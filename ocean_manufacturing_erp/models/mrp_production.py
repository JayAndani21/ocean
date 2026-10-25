# Copyright 2026 Ocean Technoforge
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html).

from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    consumption = fields.Selection(
        selection=[
            ("flexible", "Allowed"),
            ("warning", "Allowed with warning"),
            ("strict", "Blocked"),
        ],
        default="flexible",
    )

    def _get_consumption_issues(self):
        """Suppress consumption difference warnings since scrap and yield variations are normal in manufacturing."""
        return []

    def _action_generate_consumption_wizard(self, consumption_issues):
        """Do not generate consumption warning wizard under any circumstances."""
        return False

    def button_mark_done(self):
        """Always validate production without consumption warnings or finish wizards."""
        return super(MrpProduction, self.with_context(skip_consumption=True, skip_finish_wizard=True)).button_mark_done()
