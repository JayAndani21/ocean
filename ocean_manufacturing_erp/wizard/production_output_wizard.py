# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from urllib.parse import quote

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class OceanProductionOutputWizard(models.TransientModel):
    _name = "ocean.production.output.wizard"
    _description = "Production Output (Push / Finish) Wizard"

    wizard_mode = fields.Selection(
        selection=[
            ("push", "Push to Next Operation"),
            ("finish", "Finish Operation"),
        ],
        string="Wizard Mode",
        default="push",
        required=True,
    )
    mode = fields.Selection(
        selection=[
            ("push", "Push to Next Operation"),
            ("finish", "Finish Operation"),
        ],
        string="Mode",
        compute="_compute_mode",
        inverse="_inverse_mode",
        store=True,
    )

    @api.depends("wizard_mode")
    def _compute_mode(self):
        for rec in self:
            rec.mode = rec.wizard_mode

    def _inverse_mode(self):
        for rec in self:
            rec.wizard_mode = rec.mode
    workorder_id = fields.Many2one(
        comodel_name="mrp.workorder",
        string="Work Order",
        required=True,
        readonly=True,
    )
    production_id = fields.Many2one(
        related="workorder_id.production_id",
        string="Manufacturing Order",
        readonly=True,
    )
    product_id = fields.Many2one(
        related="workorder_id.product_id",
        string="Product",
        readonly=True,
    )
    operation_type = fields.Selection(
        related="workorder_id.operation_type",
        string="Operation",
        readonly=True,
    )
    workcenter_id = fields.Many2one(
        related="workorder_id.workcenter_id",
        string="Work Center",
        readonly=True,
    )
    planned_qty = fields.Float(
        related="workorder_id.qty_production",
        string="Planned Quantity",
        readonly=True,
    )
    already_produced_qty = fields.Float(
        related="workorder_id.qty_produced",
        string="Already Produced",
        readonly=True,
    )
    remaining_qty = fields.Float(
        related="workorder_id.qty_remaining",
        string="Remaining Quantity",
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        related="workorder_id.product_uom_id",
        string="Product UoM",
        readonly=True,
    )
    input_qty_used = fields.Float(
        string="Input Quantity Used",
        digits="Product Unit of Measure",
        compute="_compute_input_used",
        store=True,
        readonly=False,
        help="Quantity of input material or semi-finished pieces used for this output run.",
    )
    good_qty = fields.Float(
        string="Good Quantity",
        required=True,
        default=0.0,
        digits="Product Unit of Measure",
    )
    reject_qty = fields.Float(
        string="Reject Quantity",
        default=0.0,
        digits="Product Unit of Measure",
    )
    destination_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Good Destination",
        compute="_compute_locations",
        store=True,
        readonly=True,
    )
    reject_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Reject Destination",
        compute="_compute_locations",
        store=True,
        readonly=True,
    )
    next_operation = fields.Char(
        string="Next Operation",
        compute="_compute_next_operation",
        readonly=True,
    )
    remarks = fields.Text(
        string="Notes",
    )
    previous_remarks = fields.Text(
        string="Previous Operation Notes",
        compute="_compute_previous_remarks",
        readonly=True,
    )
    send_whatsapp = fields.Boolean(
        string="Send WhatsApp Update",
        default=True,
        help="Enable to prepare and send a WhatsApp update for this operation.",
    )
    whatsapp_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Recipient Contact",
        compute="_compute_whatsapp_recipient",
        store=True,
        readonly=False,
        help="Contact person to receive the WhatsApp message.",
    )
    whatsapp_phone = fields.Char(
        string="WhatsApp Phone",
        compute="_compute_whatsapp_phone",
        store=True,
        readonly=False,
        help="Phone number with country code (e.g. 919876543210). Leave blank to select contact/group in WhatsApp.",
    )
    whatsapp_message = fields.Text(
        string="WhatsApp Message",
        compute="_compute_whatsapp_message",
        store=True,
        readonly=False,
        help="Editable preview of the message that will be sent via WhatsApp.",
    )

    @api.depends("workorder_id")
    def _compute_whatsapp_recipient(self):
        for wizard in self:
            wo = wizard.workorder_id
            if not wo:
                wizard.whatsapp_partner_id = False
                continue
            partner = False
            next_wo = wo._get_next_workorder() if hasattr(wo, "_get_next_workorder") else False
            if next_wo and hasattr(next_wo.workcenter_id, "manager_id") and next_wo.workcenter_id.manager_id:
                partner = next_wo.workcenter_id.manager_id.partner_id
            elif wo.production_id and wo.production_id.user_id:
                partner = wo.production_id.user_id.partner_id
            elif wizard.env.user:
                partner = wizard.env.user.partner_id
            wizard.whatsapp_partner_id = partner

    def _extract_partner_phone(self, partner):
        if not partner:
            return ""
        return (
            getattr(partner, "mobile", False)
            or getattr(partner, "phone", False)
            or ""
        )

    def _extract_user_phone(self, user):
        if not user:
            return ""
        return (
            getattr(user, "mobile", False)
            or getattr(user, "phone", False)
            or self._extract_partner_phone(getattr(user, "partner_id", False))
            or ""
        )

    @api.depends("whatsapp_partner_id")
    def _compute_whatsapp_phone(self):
        for wizard in self:
            if wizard.whatsapp_partner_id:
                wizard.whatsapp_phone = wizard._extract_partner_phone(wizard.whatsapp_partner_id)
            elif not wizard.whatsapp_phone:
                user = (wizard.workorder_id and wizard.workorder_id.production_id.user_id) or wizard.env.user
                wizard.whatsapp_phone = wizard._extract_user_phone(user)

    @api.onchange("whatsapp_partner_id")
    def _onchange_whatsapp_partner_id(self):
        if self.whatsapp_partner_id:
            self.whatsapp_phone = self._extract_partner_phone(self.whatsapp_partner_id)

    def _build_default_whatsapp_message(self):
        self.ensure_one()
        wo = self.workorder_id
        if not wo:
            return ""

        mo_name = wo.production_id.name or _("N/A")
        op_name = wo.name or (wo.operation_id and wo.operation_id.name) or _("Operation")
        product_name = wo.product_id.display_name or (wo.product_id and wo.product_id.name) or _("N/A")
        uom_name = wo.product_uom_id.name or "PCS"
        good_qty_str = f"{self.good_qty:g}"
        reject_qty_str = f"{self.reject_qty:g}"
        next_stage = self.next_operation or _("Completed")

        msg_lines = [
            "🏭 *Ocean Technoforge - Production Report*",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📋 *MO:* {mo_name}",
            f"⚙️ *Operation:* {op_name}",
            f"📦 *Product:* {product_name}",
            f"✅ *Good Output:* {good_qty_str} {uom_name}",
        ]
        if self.reject_qty > 0:
            msg_lines.append(f"❌ *Reject / Scrap:* {reject_qty_str} {uom_name}")

        msg_lines.append(f"📍 *Next Stage:* {next_stage}")

        if self.remarks and self.remarks.strip():
            msg_lines.append(f"📝 *Remarks:* {self.remarks.strip()}")

        status_str = "Finalized" if self.wizard_mode == "finish" else "In Progress (Partial Output)"
        msg_lines.append(f"📌 *Status:* {status_str}")
        msg_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(msg_lines)

    @api.depends("workorder_id", "good_qty", "reject_qty", "remarks", "next_operation", "wizard_mode")
    def _compute_whatsapp_message(self):
        for wizard in self:
            wizard.whatsapp_message = wizard._build_default_whatsapp_message()

    @api.onchange("good_qty", "reject_qty", "remarks")
    def _onchange_whatsapp_output_fields(self):
        if self.workorder_id:
            self.whatsapp_message = self._build_default_whatsapp_message()

    def _clean_phone_number(self, phone):
        if not phone:
            return ""
        return "".join(filter(str.isdigit, phone))

    def _get_whatsapp_redirect_url(self):
        self.ensure_one()
        clean_phone = self._clean_phone_number(self.whatsapp_phone)
        encoded_text = quote(self.whatsapp_message or "")
        if clean_phone:
            return f"https://api.whatsapp.com/send?phone={clean_phone}&text={encoded_text}"
        return f"https://api.whatsapp.com/send?text={encoded_text}"

    def action_confirm_and_whatsapp(self):
        """Confirm production output and redirect to WhatsApp Web / App."""
        return self.with_context(open_whatsapp=True).action_confirm_output()

    @api.depends("workorder_id")
    def _compute_previous_remarks(self):
        for wizard in self:
            if wizard.workorder_id and hasattr(wizard.workorder_id, "_get_previous_remarks"):
                wizard.previous_remarks = wizard.workorder_id._get_previous_remarks()
            else:
                wizard.previous_remarks = ""

    is_first_operation = fields.Boolean(
        string="Is First Operation",
        compute="_compute_is_first_operation",
    )

    @api.depends("workorder_id")
    def _compute_is_first_operation(self):
        for wizard in self:
            wo = wizard.workorder_id
            if not wo:
                wizard.is_first_operation = True
                continue
            prev_wo = wo._get_previous_workorder() if hasattr(wo, "_get_previous_workorder") else False
            op_type = wo._get_effective_operation_type() if hasattr(wo, "_get_effective_operation_type") else (wo.operation_type or "cutting")
            wizard.is_first_operation = (not prev_wo) and (op_type == "cutting")

    @api.depends("workorder_id", "good_qty", "reject_qty", "operation_type")
    def _compute_input_used(self):
        for wizard in self:
            wo = wizard.workorder_id
            if not wo:
                wizard.input_qty_used = 0.0
                continue
            total_out = wizard.good_qty + wizard.reject_qty
            prev_wo = wo._get_previous_workorder() if hasattr(wo, "_get_previous_workorder") else False
            op_type = wo._get_effective_operation_type() if hasattr(wo, "_get_effective_operation_type") else (wo.operation_type or "cutting")
            is_initial_cutting = (not prev_wo) and (op_type == "cutting")

            if is_initial_cutting:
                raw_moves = wo.move_raw_ids or wo.production_id.move_raw_ids
                unit_factor = raw_moves[:1].unit_factor if raw_moves else 1.0
                wizard.input_qty_used = total_out * unit_factor
            else:
                wizard.input_qty_used = total_out

    @api.depends("workorder_id", "operation_type")
    def _compute_locations(self):
        for wizard in self:
            wo = wizard.workorder_id
            if not wo:
                wizard.destination_location_id = False
                wizard.reject_location_id = False
                continue

            company = wo.company_id or self.env.company
            wizard.destination_location_id = wo._get_operation_location("dest")

            # Look up standard scrap / inventory loss location
            scrap_loc = self.env["stock.location"].search([
                ("company_id", "in", (False, company.id)),
                ("usage", "=", "inventory"),
                "|",
                ("name", "=ilike", "%Scrap%"),
                ("complete_name", "=ilike", "%Scrap%"),
            ], limit=1)
            if not scrap_loc:
                scrap_loc = self.env["stock.location"].search([
                    ("company_id", "in", (False, company.id)),
                    ("usage", "=", "inventory"),
                ], limit=1)
            wizard.reject_location_id = scrap_loc

    @api.depends("workorder_id")
    def _compute_next_operation(self):
        for wizard in self:
            wo = wizard.workorder_id
            if not wo or not wo.production_id:
                wizard.next_operation = False
                continue

            next_wo = wo._get_next_workorder() if hasattr(wo, "_get_next_workorder") else False
            if next_wo:
                wizard.next_operation = next_wo.name
            else:
                wizard.next_operation = _("Finished Goods / Stock")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        wo_id = (
            res.get("workorder_id")
            or self.env.context.get("default_workorder_id")
            or (self.env.context.get("active_model") == "mrp.workorder" and self.env.context.get("active_id"))
            or (self.env.context.get("active_model") == "mrp.workorder" and self.env.context.get("active_ids") and self.env.context.get("active_ids")[0])
        )
        if wo_id:
            res["workorder_id"] = wo_id
            wo = self.env["mrp.workorder"].browse(wo_id)
            if "good_qty" in fields_list and not res.get("good_qty"):
                if wo.operation_type != "cutting" and wo.input_qty > 0:
                    res["good_qty"] = max(0.0, wo.input_qty - wo.qty_produced)
                else:
                    res["good_qty"] = wo.qty_remaining

            partner = (wo.production_id and wo.production_id.user_id and wo.production_id.user_id.partner_id) or self.env.user.partner_id
            phone = (getattr(partner, "mobile", False) or getattr(partner, "phone", False) or "") if partner else ""
            res["whatsapp_partner_id"] = partner.id if partner else False
            res["whatsapp_phone"] = phone
            res["send_whatsapp"] = True

        mode_val = (
            res.get("wizard_mode")
            or res.get("mode")
            or self.env.context.get("default_wizard_mode")
            or self.env.context.get("default_mode")
            or self.env.context.get("wizard_mode")
            or self.env.context.get("mode")
            or "push"
        )
        res["wizard_mode"] = mode_val
        res["mode"] = mode_val
        return res

    def action_confirm_output(self):
        """
        Record production output (Push or Finish):
        1. Validate quantities.
        2. Create proper stock movements (consumption + output + reject).
        3. Update workorder qty_produced and state.
        4. Hand-off good quantity to next work order.
        5. Update workorder session.
        """
        self.ensure_one()
        wo = self.workorder_id

        if not wo:
            raise UserError(_("No active work order associated with this entry."))

        if self.good_qty < 0 or self.reject_qty < 0:
            raise UserError(_("Good and Reject quantities cannot be negative."))

        total_output = self.good_qty + self.reject_qty
        if self.wizard_mode == "push" and total_output <= 0:
            raise UserError(_("Total output (Good + Reject) must be strictly greater than zero."))
        if self.wizard_mode == "finish" and total_output <= 0 and wo.qty_remaining > 0:
            raise UserError(_("Total output (Good + Reject) must be strictly greater than zero when remaining quantity exists."))

        if self.wizard_mode == "push":
            if self.already_produced_qty + self.good_qty > self.planned_qty:
                raise UserError(
                    _("Good quantity (%(good)s) plus already produced (%(done)s) exceeds planned target (%(planned)s).",
                      good=self.good_qty,
                      done=self.already_produced_qty,
                      planned=self.planned_qty)
                )

        # 1. Identify locations
        prod_location = (
            wo.product_id.property_stock_production
            or wo.production_id.production_location_id
            or self.env.ref("stock.location_production", raise_if_not_found=False)
        )
        if not prod_location:
            prod_location = self.env["stock.location"].search([("usage", "=", "production")], limit=1)

        source_loc = wo._get_operation_location("source")
        dest_loc = self.destination_location_id
        scrap_loc = self.reject_location_id

        if not dest_loc:
            raise UserError(_("Destination WIP location could not be determined for operation '%s'.") % wo.name)
        if self.reject_qty > 0 and not scrap_loc:
            raise UserError(_("Scrap location could not be determined for rejected output."))

        created_moves = self.env["stock.move"]

        prev_wo = wo._get_previous_workorder() if hasattr(wo, "_get_previous_workorder") else False
        op_type = wo._get_effective_operation_type() if hasattr(wo, "_get_effective_operation_type") else (wo.operation_type or "cutting")
        is_initial_cutting = (not prev_wo) and (op_type == "cutting")

        # 2. Process stock movements
        if is_initial_cutting:
            # Cutting: Consume raw material from MO's move_raw_ids (KG)
            raw_move = wo.production_id.move_raw_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
            )[:1]

            if not raw_move:
                raise UserError(_("No active raw material component move found on Manufacturing Order '%s'.") % wo.production_id.name)

            raw_product = raw_move.product_id
            unit_factor = raw_move.unit_factor or 1.0

            # Calculate raw consumption in KG
            if self.input_qty_used > 0:
                raw_qty_to_consume = self.input_qty_used
            else:
                raw_qty_to_consume = total_output * unit_factor

            # Consume from the existing MO move_raw_id (prevents duplicate stock moves)
            raw_move.write({
                "quantity": raw_qty_to_consume,
                "picked": True,
                "manual_consumption": True,
            })
            if float_compare(raw_qty_to_consume, raw_move.product_uom_qty, precision_rounding=raw_product.uom_id.rounding) < 0:
                raw_move._action_done(cancel_backorder=False)
            else:
                raw_move._action_done()
            created_moves |= raw_move

            # Produce good cut pieces to Cutting WIP (PCS)
            if self.good_qty > 0:
                good_move = self.env["stock.move"].create({
                    "description_picking": _("PROD:%(mo)s - %(op)s - Good", mo=wo.production_id.name, op=wo.name),
                    "product_id": wo.product_id.id,
                    "product_uom": wo.product_uom_id.id,
                    "product_uom_qty": self.good_qty,
                    "location_id": prod_location.id,
                    "location_dest_id": dest_loc.id,
                    "origin": wo.production_id.name,
                    "company_id": wo.company_id.id,
                    "procure_method": "make_to_stock",
                })
                good_move._action_confirm()
                good_move.write({"quantity": self.good_qty, "picked": True})
                good_move._action_done()
                created_moves |= good_move

            # Produce reject cut pieces to Scrap (PCS)
            if self.reject_qty > 0:
                reject_move = self.env["stock.move"].create({
                    "description_picking": _("PROD:%(mo)s - %(op)s - Scrap", mo=wo.production_id.name, op=wo.name),
                    "product_id": wo.product_id.id,
                    "product_uom": wo.product_uom_id.id,
                    "product_uom_qty": self.reject_qty,
                    "location_id": prod_location.id,
                    "location_dest_id": scrap_loc.id,
                    "origin": wo.production_id.name,
                    "company_id": wo.company_id.id,
                    "procure_method": "make_to_stock",
                })
                reject_move._action_confirm()
                reject_move.write({"quantity": self.reject_qty, "picked": True})
                reject_move._action_done()
                created_moves |= reject_move

        else:
            # Subsequent operations (Forging, CNC, VMC, Inspection, Packing): Input & Output in PCS
            consumed_pieces = self.input_qty_used if self.input_qty_used > 0 else (self.good_qty + self.reject_qty)

            # Consume pieces from previous WIP to Production
            consume_wip_move = self.env["stock.move"].create({
                "description_picking": _("PROD:%(mo)s - %(op)s - Consumption", mo=wo.production_id.name, op=wo.name),
                "product_id": wo.product_id.id,
                "product_uom": wo.product_uom_id.id,
                "product_uom_qty": consumed_pieces,
                "location_id": source_loc.id,
                "location_dest_id": prod_location.id,
                "origin": wo.production_id.name,
                "company_id": wo.company_id.id,
                "procure_method": "make_to_stock",
            })
            consume_wip_move._action_confirm()
            consume_wip_move.write({"quantity": consumed_pieces, "picked": True})
            consume_wip_move._action_done()
            created_moves |= consume_wip_move

            # Produce good pieces to destination WIP
            if self.good_qty > 0:
                produce_good_move = self.env["stock.move"].create({
                    "description_picking": _("PROD:%(mo)s - %(op)s - Good", mo=wo.production_id.name, op=wo.name),
                    "product_id": wo.product_id.id,
                    "product_uom": wo.product_uom_id.id,
                    "product_uom_qty": self.good_qty,
                    "location_id": prod_location.id,
                    "location_dest_id": dest_loc.id,
                    "origin": wo.production_id.name,
                    "company_id": wo.company_id.id,
                    "procure_method": "make_to_stock",
                })
                produce_good_move._action_confirm()
                produce_good_move.write({"quantity": self.good_qty, "picked": True})
                produce_good_move._action_done()
                created_moves |= produce_good_move

            # Produce reject pieces to Scrap
            if self.reject_qty > 0:
                reject_wip_move = self.env["stock.move"].create({
                    "description_picking": _("PROD:%(mo)s - %(op)s - Scrap", mo=wo.production_id.name, op=wo.name),
                    "product_id": wo.product_id.id,
                    "product_uom": wo.product_uom_id.id,
                    "product_uom_qty": self.reject_qty,
                    "location_id": prod_location.id,
                    "location_dest_id": scrap_loc.id,
                    "origin": wo.production_id.name,
                    "company_id": wo.company_id.id,
                    "procure_method": "make_to_stock",
                })
                reject_wip_move._action_confirm()
                reject_wip_move.write({"quantity": self.reject_qty, "picked": True})
                reject_wip_move._action_done()
                created_moves |= reject_wip_move
        # 3. Update Work Order state and quantities
        new_produced = wo.qty_produced + self.good_qty
        wo_write_vals = {
            "qty_produced": new_produced,
        }
        if self.remarks:
            existing_remarks = wo.remarks or ""
            if self.remarks not in existing_remarks:
                wo_write_vals["remarks"] = f"{existing_remarks}\n{self.remarks}".strip() if existing_remarks else self.remarks
        wo.write(wo_write_vals)

        # 4. Hand-off good quantity to the next work order in sequence
        next_wo = wo._get_next_workorder() if hasattr(wo, "_get_next_workorder") else False
        if next_wo:
            next_input = (next_wo.input_qty or 0.0) + self.good_qty
            next_vals = {
                "input_qty": next_input,
            }
            # When completing the current work order, synchronize the downstream planned target
            # to match the cumulative good pieces produced from this stage
            if self.wizard_mode == "finish":
                next_vals["qty_production"] = new_produced
            next_wo.write(next_vals)

            next_session = self.env["mrp.workorder.session"]._get_or_create_session(next_wo)
            next_session.write({"input_qty": next_input})
        else:
            # If this is the final operation of the MO (e.g. VMC or Packing), update MO's producing quantity
            if wo.production_id:
                wo.production_id.write({
                    "qty_producing": new_produced,
                })

        # 5. Update session tracking
        session = self.env["mrp.workorder.session"]._get_or_create_session(wo)
        session_vals = {
            "current_output_qty": new_produced,
            "current_reject_qty": session.current_reject_qty + self.reject_qty,
            "remarks": self.remarks,
        }

        if self.wizard_mode == "finish":
            session_vals.update({
                "final_output_qty": new_produced,
                "final_reject_qty": session.final_reject_qty + self.reject_qty,
                "state": "completed",
                "finish_time": fields.Datetime.now(),
            })
            session.write(session_vals)
            wo.is_production_completed = True
            # Complete the workorder
            if wo.state not in ("done", "cancel"):
                wo.with_context(skip_finish_wizard=True).button_finish()
        else:
            # PUSH mode: keep In Progress if remaining quantity exists
            if wo.qty_remaining <= 0:
                session_vals.update({
                    "state": "completed",
                    "finish_time": fields.Datetime.now(),
                })
                session.write(session_vals)
                wo.is_production_completed = True
                if wo.state not in ("done", "cancel"):
                    wo.with_context(skip_finish_wizard=True).button_finish()
            else:
                session_vals["state"] = "in_progress"
                session.write(session_vals)
                # Ensure workorder stays in 'progress' state
                if wo.state != "progress":
                    wo.write({"state": "progress"})

        if self.env.context.get("open_whatsapp"):
            if wo.production_id:
                chatter_msg = _(
                    "<b>📱 WhatsApp Production Update Opened</b><br/>"
                    "<b>Operation:</b> %(op)s<br/>"
                    "<b>Recipient:</b> %(phone)s<br/>"
                    "<b>Message Content:</b><br/><pre>%(msg)s</pre>",
                    op=wo.name,
                    phone=self.whatsapp_phone or _("Contact/Group Selected in WhatsApp"),
                    msg=self.whatsapp_message or "",
                )
                wo.production_id.message_post(body=chatter_msg, message_type="notification")

            whatsapp_url = self._get_whatsapp_redirect_url()
            return {
                "type": "ir.actions.act_url",
                "url": whatsapp_url,
                "target": "new",
            }

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Production Recorded"),
                "message": _("Successfully recorded %(good)s %(uom)s to %(loc)s.",
                             good=self.good_qty,
                             uom=wo.product_uom_id.name,
                             loc=dest_loc.display_name),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            }
        }
