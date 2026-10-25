# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class OceanProductionStartWizard(models.TransientModel):
    _name = "ocean.production.start.wizard"
    _description = "Start Production Wizard"

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
    operation_id = fields.Many2one(
        related="workorder_id.operation_id",
        string="Operation",
        readonly=True,
    )
    operation_type = fields.Selection(
        related="workorder_id.operation_type",
        string="Operation Type",
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
    input_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Input Material / WIP",
        compute="_compute_input_material",
        store=True,
        readonly=True,
    )
    input_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Input UoM",
        compute="_compute_input_material",
        store=True,
        readonly=True,
    )
    source_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Source Location",
        compute="_compute_input_material",
        store=True,
        readonly=True,
    )
    available_qty = fields.Float(
        string="Available Quantity",
        compute="_compute_available_qty",
        digits="Product Unit of Measure",
        readonly=True,
    )
    input_qty = fields.Float(
        string="Input Quantity",
        required=True,
        digits="Product Unit of Measure",
    )
    prev_workorder_id = fields.Many2one(
        comodel_name="mrp.workorder",
        string="Previous Work Order",
        compute="_compute_prev_workorder",
        readonly=True,
    )
    previous_operation_info = fields.Char(
        string="Previous Operation Info",
        readonly=True,
    )
    previous_good_qty = fields.Float(
        string="Previous Good Quantity",
        readonly=True,
        digits="Product Unit of Measure",
    )
    previous_remarks = fields.Text(
        string="Previous Operation Notes",
        compute="_compute_previous_remarks",
        readonly=True,
    )
    operator_id = fields.Many2one(
        comodel_name="res.users",
        string="Operator",
        default=lambda self: self.env.user,
        readonly=True,
    )

    is_first_operation = fields.Boolean(
        string="Is First Operation",
        compute="_compute_is_first_operation",
    )

    @api.depends("workorder_id")
    def _compute_previous_remarks(self):
        for wizard in self:
            if wizard.workorder_id and hasattr(wizard.workorder_id, "_get_previous_remarks"):
                wizard.previous_remarks = wizard.workorder_id._get_previous_remarks()
            else:
                wizard.previous_remarks = ""

    @api.depends("workorder_id")
    def _compute_prev_workorder(self):
        for wizard in self:
            if wizard.workorder_id and hasattr(wizard.workorder_id, "_get_previous_workorder"):
                wizard.prev_workorder_id = wizard.workorder_id._get_previous_workorder()
            else:
                wizard.prev_workorder_id = False

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

    @api.depends("workorder_id", "operation_type")
    def _compute_input_material(self):
        for wizard in self:
            wo = wizard.workorder_id
            if not wo:
                wizard.input_product_id = False
                wizard.input_uom_id = False
                wizard.source_location_id = False
                continue

            prev_wo = wo._get_previous_workorder() if hasattr(wo, "_get_previous_workorder") else False
            op_type = wo._get_effective_operation_type() if hasattr(wo, "_get_effective_operation_type") else (wo.operation_type or "cutting")

            # It is the initial raw-material cutting step ONLY if there is NO previous work order AND op_type is cutting
            if not prev_wo and op_type == "cutting":
                raw_move = wo.move_raw_ids or wo.production_id.move_raw_ids
                input_prod = raw_move[:1].product_id if raw_move else False
                wizard.input_product_id = input_prod
                wizard.input_uom_id = input_prod.uom_id if input_prod else False
                wizard.source_location_id = wo._get_operation_location("source")
            else:
                # For all subsequent operations (Forging, CNC, VMC, etc.):
                # Input product is the semi-finished piece (the finished product being manufactured, in PCS)
                wizard.input_product_id = wo.product_id
                wizard.input_uom_id = wo.product_uom_id or wo.product_id.uom_id
                wizard.source_location_id = wo._get_operation_location("source")

    @api.depends("input_product_id", "source_location_id")
    def _compute_available_qty(self):
        for wizard in self:
            if wizard.input_product_id and wizard.source_location_id:
                quants = self.env["stock.quant"].search([
                    ("product_id", "=", wizard.input_product_id.id),
                    ("location_id", "child_of", wizard.source_location_id.id),
                ])
                wizard.available_qty = sum(quants.mapped("quantity"))
            else:
                wizard.available_qty = 0.0

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
            prev_wo = wo._get_previous_workorder() if hasattr(wo, "_get_previous_workorder") else False
            op_type = wo._get_effective_operation_type() if hasattr(wo, "_get_effective_operation_type") else (wo.operation_type or "cutting")
            is_initial_cutting = (not prev_wo) and op_type == "cutting"

            prev_good = 0.0
            if prev_wo:
                res["prev_workorder_id"] = prev_wo.id
                prev_good = prev_wo.qty_produced
                res["previous_good_qty"] = prev_good
                uom_name = prev_wo.product_uom_id.name or wo.product_uom_id.name or "Units"
                res["previous_operation_info"] = _("From Previous Operation (%(op)s): %(qty)s %(uom)s produced",
                                                   op=prev_wo.name,
                                                   qty=prev_good,
                                                   uom=uom_name)

            if "input_qty" in fields_list and not res.get("input_qty"):
                if is_initial_cutting:
                    raw_moves = wo.move_raw_ids or wo.production_id.move_raw_ids
                    if raw_moves:
                        unit_factor = raw_moves[:1].unit_factor or 1.0
                        res["input_qty"] = wo.qty_remaining * unit_factor
                    else:
                        res["input_qty"] = wo.qty_remaining
                else:
                    # Subsequent operations (Forging, CNC, VMC):
                    # Must be in PCS (same UoM as product_uom_id)
                    # Priority 1: wo.input_qty if already handed off from previous operation
                    # Priority 2: previous operation good qty (prev_good)
                    # Priority 3: previous operation produced qty minus what this wo already produced
                    # Priority 4: standard qty_remaining or qty_production
                    if wo.input_qty > 0:
                        res["input_qty"] = wo.input_qty
                    elif prev_good > 0:
                        res["input_qty"] = max(0.0, prev_good - wo.qty_produced)
                    elif prev_wo and prev_wo.qty_produced > 0:
                        res["input_qty"] = max(0.0, prev_wo.qty_produced - wo.qty_produced)
                    else:
                        res["input_qty"] = wo.qty_remaining or wo.qty_production
        return res

    def action_start_production(self):
        """Validate input quantity and stock, then start the work order."""
        self.ensure_one()
        wo = self.workorder_id

        if self.input_qty <= 0:
            raise UserError(_("Input quantity must be strictly greater than zero."))

        if self.source_location_id and self.source_location_id.usage != "internal":
            raise UserError(_("The source location '%s' must be an internal warehouse location.") % self.source_location_id.display_name)

        if self.available_qty > 0 and self.input_qty > self.available_qty:
            raise UserError(
                _("Input quantity (%(input)s %(uom)s) cannot exceed available quantity (%(avail)s %(uom)s) at location '%(loc)s'.",
                  input=self.input_qty,
                  uom=self.input_uom_id.name,
                  avail=self.available_qty,
                  loc=self.source_location_id.display_name)
            )

        if wo.state in ("done", "cancel"):
            raise UserError(_("Cannot start a work order that is already completed or cancelled."))

        # Delegate start execution and session recording to work order
        wo.action_start_workorder(
            self.input_qty,
            self.source_location_id.id if self.source_location_id else False,
        )
        return {"type": "ir.actions.act_window_close"}
