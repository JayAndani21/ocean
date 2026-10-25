# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    operation_type = fields.Selection(
        related="operation_id.operation_type",
        string="Operation Type",
        store=True,
        readonly=False,
    )
    input_qty = fields.Float(
        string="Input Quantity",
        default=0.0,
        digits="Product Unit of Measure",
        help="Input quantity received for this work order operation.",
    )
    is_production_completed = fields.Boolean(
        string="Production Entry Completed",
        default=False,
        copy=False,
        help="Technical flag indicating whether production entry was completed.",
    )
    remarks = fields.Text(
        string="Notes",
        help="Notes recorded for this work order operation.",
    )
    previous_remarks = fields.Text(
        string="Previous Operation Notes",
        compute="_compute_previous_remarks",
        help="Notes from the immediately preceding operation of this manufacturing order.",
    )
    session_ids = fields.One2many(
        comodel_name="mrp.workorder.session",
        inverse_name="workorder_id",
        string="Production Sessions",
    )
    current_session_id = fields.Many2one(
        comodel_name="mrp.workorder.session",
        compute="_compute_current_session_id",
        string="Current Session",
    )

    @api.depends("session_ids")
    def _compute_current_session_id(self):
        for wo in self:
            wo.current_session_id = wo.session_ids[:1] or False

    def _get_previous_remarks(self):
        """Get notes from the immediately preceding work order in sequence."""
        self.ensure_one()
        prev_wo = self._get_previous_workorder()
        if not prev_wo:
            return ""
        op_name = prev_wo.name or (prev_wo.operation_id and prev_wo.operation_id.name) or _("Previous Operation")
        notes = []
        if prev_wo.remarks and prev_wo.remarks.strip():
            notes.append(prev_wo.remarks.strip())
        for sess in prev_wo.session_ids:
            if sess.remarks and sess.remarks.strip() and sess.remarks.strip() not in notes:
                notes.append(sess.remarks.strip())
        if notes:
            return f"[{op_name}]: " + "\n".join(notes)
        return ""

    @api.depends("production_id.workorder_ids.remarks", "production_id.workorder_ids.session_ids.remarks")
    def _compute_previous_remarks(self):
        for wo in self:
            wo.previous_remarks = wo._get_previous_remarks() if wo.production_id else ""

    def _get_previous_workorder(self):
        """Find the immediately preceding work order in sequence for the same MO."""
        self.ensure_one()
        prior_wos = self.production_id.workorder_ids.filtered(
            lambda w: w.sequence < self.sequence or (w.sequence == self.sequence and w.id < self.id)
        ).sorted(key=lambda w: (w.sequence, w.id), reverse=True)
        return prior_wos[:1] if prior_wos else self.env["mrp.workorder"]

    def _get_next_workorder(self):
        """Find the immediately following work order in sequence for the same MO."""
        self.ensure_one()
        subsequent_wos = self.production_id.workorder_ids.filtered(
            lambda w: w.sequence > self.sequence or (w.sequence == self.sequence and w.id > self.id)
        ).sorted(key=lambda w: (w.sequence, w.id))
        return subsequent_wos[:1] if subsequent_wos else self.env["mrp.workorder"]

    def _get_effective_operation_type(self):
        """
        Determine the real operation type:
        1. Infer from operation name or workcenter name (cutting, forging, cnc, vmc, inspection, packing).
        2. Fall back to operation_type field.
        3. If it has a previous work order, it cannot be the initial raw-material cutting step.
        """
        self.ensure_one()
        op_name = (self.name or (self.operation_id and self.operation_id.name) or "").lower()
        wc_name = (self.workcenter_id and self.workcenter_id.name or "").lower()

        for key in ["forging", "cnc", "vmc", "inspection", "packing", "cutting"]:
            if key in op_name or key in wc_name:
                return key

        if self.operation_type and self.operation_type != "cutting":
            return self.operation_type

        # If it has a previous work order, it cannot be the initial raw-material cutting step
        if self._get_previous_workorder():
            return "forging"

        return self.operation_type or "cutting"

    def button_start(self, raise_on_invalid_state=False):
        """Intercept Start click to open the Start Production Wizard modal."""
        if len(self) == 1:
            if self.state in ("done", "cancel"):
                if raise_on_invalid_state:
                    return super().button_start(raise_on_invalid_state=raise_on_invalid_state)
                raise UserError(_("You cannot start a work order that is already done or cancelled."))
            # If the user is already working on this in-progress workorder, let standard timer handle it
            if self.state == "progress" and self.is_user_working:
                return super().button_start(raise_on_invalid_state=raise_on_invalid_state)
            return self.action_open_start_wizard()
        return super().button_start(raise_on_invalid_state=raise_on_invalid_state)

    def button_finish(self):
        """Override button_finish so any finish trigger opens the Finish wizard unless skip_finish_wizard is set."""
        if len(self) == 1 and not self.env.context.get("skip_finish_wizard") and not self.is_production_completed:
            if self.state == "progress":
                return self.action_open_finish_wizard()
        return super().button_finish()

    def action_start_workorder(self, input_qty, source_location_id):
        """Called upon Start Wizard confirmation: start timer, set state to progress, and record session."""
        self.ensure_one()
        session = self.env["mrp.workorder.session"]._get_or_create_session(self)
        session.write({
            "input_qty": input_qty,
            "state": "in_progress",
            "start_time": session.start_time or fields.Datetime.now(),
        })
        self.write({
            "input_qty": input_qty,
        })
        # Execute standard Odoo timer start and state transition to 'progress'
        return super(MrpWorkorder, self).button_start()

    def action_open_start_wizard(self):
        """Open Start Production Wizard."""
        self.ensure_one()
        return {
            "name": _("Start Production - %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "ocean.production.start.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "mrp.workorder",
                "active_id": self.id,
                "active_ids": self.ids,
                "default_workorder_id": self.id,
            },
        }

    def action_open_push_wizard(self):
        """Open Push Production Output Wizard."""
        self.ensure_one()
        if self.state != "progress":
            raise UserError(_("You can only push production for a work order that is In Progress."))
        return {
            "name": _("Push Production - %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "ocean.production.output.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "mrp.workorder",
                "active_id": self.id,
                "active_ids": self.ids,
                "default_workorder_id": self.id,
                "default_wizard_mode": "push",
                "default_mode": "push",
            },
        }

    def action_open_finish_wizard(self):
        """Open Finish Production Output Wizard."""
        self.ensure_one()
        if self.state != "progress":
            raise UserError(_("You can only finish a work order that is In Progress."))
        return {
            "name": _("Finish Operation - %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "ocean.production.output.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "mrp.workorder",
                "active_id": self.id,
                "active_ids": self.ids,
                "default_workorder_id": self.id,
                "default_wizard_mode": "finish",
                "default_mode": "finish",
            },
        }

    def _get_operation_location(self, location_type="dest"):
        """
        Dynamically determine source or destination location for this operation.
        Follows company's location naming convention:
        - Cutting: source = Raw Material, dest = Cutting WIP
        - Forging: source = Cutting WIP, dest = Forging WIP
        - CNC: source = Forging WIP, dest = CNC WIP
        - VMC: source = CNC WIP, dest = VMC WIP
        - Inspection: source = VMC WIP, dest = Inspection
        - Packing: source = Inspection, dest = Finished Goods
        """
        self.ensure_one()
        company = self.company_id or self.env.company

        # If this is the last operation of the MO and looking for destination,
        # route output directly to Finished Goods / MO destination location.
        if location_type == "dest":
            next_wo = self._get_next_workorder()
            if not next_wo:
                return self.production_id.location_dest_id

        loc_mapping = {
            "cutting": {"source": "Raw Material", "dest": "Cutting WIP"},
            "forging": {"source": "Cutting WIP", "dest": "Forging WIP"},
            "cnc": {"source": "Forging WIP", "dest": "CNC WIP"},
            "vmc": {"source": "CNC WIP", "dest": "VMC WIP"},
            "inspection": {"source": "VMC WIP", "dest": "Inspection"},
            "packing": {"source": "Inspection", "dest": "Finished Goods"},
        }

        op = self._get_effective_operation_type() if hasattr(self, "_get_effective_operation_type") else (self.operation_type or "cutting")

        # For subsequent operations (has previous work order), source MUST be previous operation's destination WIP
        if location_type == "source":
            prev_wo = self._get_previous_workorder()
            if prev_wo:
                prev_op = prev_wo._get_effective_operation_type() if hasattr(prev_wo, "_get_effective_operation_type") else (prev_wo.operation_type or "cutting")
                prev_target_name = loc_mapping.get(prev_op, {}).get("dest")
                if prev_target_name:
                    location = self.env["stock.location"].search([
                        ("company_id", "in", (False, company.id)),
                        ("usage", "=", "internal"),
                        "|",
                        ("name", "=ilike", prev_target_name),
                        ("complete_name", "=ilike", f"%{prev_target_name}%"),
                    ], limit=1)
                    if location:
                        return location
                # Fallback to standard MO stock location (WH/Stock)
                return self.production_id.location_src_id

        target_name = loc_mapping.get(op, {}).get(location_type)

        if target_name:
            location = self.env["stock.location"].search([
                ("company_id", "in", (False, company.id)),
                ("usage", "=", "internal"),
                "|",
                ("name", "=ilike", target_name),
                ("complete_name", "=ilike", f"%{target_name}%"),
            ], limit=1)
            if location:
                return location

        # Fallback to standard MO locations if custom WIP location not yet created
        if location_type == "source":
            return self.production_id.location_src_id
        return self.production_id.location_dest_id
