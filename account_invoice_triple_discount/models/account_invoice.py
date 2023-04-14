# Copyright 2017 Tecnativa - David Vidal
# Copyright 2017 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    discounting_type = fields.Selection(
        related='partner_id.discounting_type',
    )

    # I cannot find a way less intrusive than this one at the moment to force tax calculation
    # to be correct when this module is installed, otherwise a discrepancy of some cents will
    # appear on some cases causing the related e-invoice to be rejected when sent.
    # However, this has to be considered nothing more that a workaround: it fixes the
    # account_invoice but leaves the account_invoice_tax lines wrong as before.
    @api.one
    @api.depends('invoice_line_ids.price_subtotal', 'tax_line_ids.amount', 'tax_line_ids.amount_rounding',
                 'currency_id', 'company_id', 'date_invoice', 'type', 'date')
    def _compute_amount(self):
        self.amount_untaxed = sum(line.price_subtotal for line in self.invoice_line_ids)
        # Calculate amount_tax from our get_taxes_values()
        self.amount_tax = sum([self.get_taxes_values()[key]['amount'] for key in self.get_taxes_values().keys()])
        self.amount_total = self.amount_untaxed + self.amount_tax
        amount_total_company_signed = self.amount_total
        amount_untaxed_signed = self.amount_untaxed
        if self.currency_id and self.company_id and self.currency_id != self.company_id.currency_id:
            currency_id = self.currency_id
            rate_date = self._get_currency_rate_date() or fields.Date.today()
            amount_total_company_signed = currency_id._convert(self.amount_total, self.company_id.currency_id, self.company_id, rate_date)
            amount_untaxed_signed = currency_id._convert(self.amount_untaxed, self.company_id.currency_id, self.company_id, rate_date)
        sign = self.type in ['in_refund', 'out_refund'] and -1 or 1
        self.amount_total_company_signed = amount_total_company_signed * sign
        self.amount_total_signed = self.amount_total * sign
        self.amount_untaxed_signed = amount_untaxed_signed * sign
        # Force residual re-calculation
        super(AccountInvoice, self)._compute_residual()

    def get_taxes_values(self):
        lines = self.invoice_line_ids
        prev_values = lines.triple_discount_preprocess()
        tax_grouped = super().get_taxes_values()
        lines.triple_discount_postprocess(prev_values)
        return tax_grouped

    @api.onchange('partner_id', 'company_id')
    def _onchange_partner_id(self):
        self.ensure_one()
        res = super()._onchange_partner_id()
        partner_discounting_type = self.partner_id.discounting_type
        if partner_discounting_type:
            self.invoice_line_ids.update({
                'discounting_type': partner_discounting_type,
            })
        return res


class AccountInvoiceLine(models.Model):
    _name = "account.invoice.line"
    _inherit = ["line.triple_discount.mixin", "account.invoice.line"]

    @api.multi
    @api.depends('discount2', 'discount3', 'discounting_type')
    def _compute_price(self):
        for line in self:
            prev_values = line.triple_discount_preprocess()
            super(AccountInvoiceLine, line)._compute_price()
            line.triple_discount_postprocess(prev_values)
