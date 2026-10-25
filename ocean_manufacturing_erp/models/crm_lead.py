from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="crm_lead_drawing_attachment_rel",
        column1="lead_id",
        column2="attachment_id",
        string="Attachments",
        help="Upload drawing files (PDF, STEP, etc.)",
    )

    material_grade_id = fields.Many2one(
        comodel_name="ocean.material.grade",
        string="Material Grade",
        help="Select the material grade for this lead.",
    )

    section_size = fields.Integer(
        string="Section Size",
        help="Specify the section size in mm.",
    )

    section_type_id = fields.Many2one(
        comodel_name="ocean.section.type",
        string="Section Type",
        help="Select the section type for this lead.",
    )
