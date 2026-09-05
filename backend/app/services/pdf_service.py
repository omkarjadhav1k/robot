"""Invoice PDF generation service using ReportLab."""

from datetime import datetime
from decimal import Decimal
import os
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.billing import Bill, PaymentStatus
from app.models.business import Business


class InvoicePDFService:
    """Generates professional, styled PDF invoices for store orders."""

    DEFAULT_STORAGE_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "storage",
        "invoices",
    )

    @classmethod
    def generate_invoice_pdf(
        cls,
        bill: Bill,
        business: Optional[Business] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """
        Build and save a clean PDF invoice for the given Bill.
        Returns the absolute filesystem path to the generated PDF.
        """
        target_dir = output_dir or cls.DEFAULT_STORAGE_DIR
        os.makedirs(target_dir, exist_ok=True)

        filename = f"Invoice_{bill.bill_number}.pdf"
        filepath = os.path.join(target_dir, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        normal_style = styles["Normal"]

        title_style = ParagraphStyle(
            "InvoiceTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1e293b"),
            fontName="Helvetica-Bold",
        )

        subtitle_style = ParagraphStyle(
            "InvoiceSubtitle",
            parent=normal_style,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#64748b"),
        )

        bold_style = ParagraphStyle(
            "InvoiceBold",
            parent=normal_style,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#1e293b"),
            fontName="Helvetica-Bold",
        )

        right_bold = ParagraphStyle(
            "InvoiceRightBold",
            parent=bold_style,
            alignment=2,
        )

        story = []

        # 1. Header: Store Name & Invoice Title
        biz_name = business.name if business else "Business AI Robot Store"
        biz_type = business.business_type if business else "Retail Store"

        header_data = [
            [
                Paragraph(f"<b>{biz_name}</b><br/>{biz_type}", title_style),
                Paragraph(
                    f"<b>INVOICE</b><br/>"
                    f"<font color='#64748b'>#{bill.bill_number}</font><br/>"
                    f"<font color='#64748b'>{bill.created_at.strftime('%d %b %Y, %I:%M %p')}</font>",
                    right_bold,
                ),
            ]
        ]
        header_table = Table(header_data, colWidths=[4.0 * inch, 3.5 * inch])
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ]
            )
        )
        story.append(header_table)
        story.append(Spacer(1, 15))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=15))

        # 2. Customer & Bill Info Section
        customer_name = bill.customer.name if bill.customer else "Walk-in Customer"
        customer_phone = bill.customer.phone if (bill.customer and bill.customer.phone) else "N/A"
        payment_status_text = bill.payment_status.value
        status_color = "#16a34a" if bill.payment_status == PaymentStatus.PAID else "#d97706"

        info_data = [
            [
                Paragraph(f"<b>Billed To:</b><br/>{customer_name}<br/>Phone: {customer_phone}", subtitle_style),
                Paragraph(
                    f"<b>Payment Status:</b> <font color='{status_color}'><b>{payment_status_text}</b></font><br/>"
                    f"<b>Source:</b> {bill.source.value}",
                    subtitle_style,
                ),
            ]
        ]
        info_table = Table(info_data, colWidths=[4.0 * inch, 3.5 * inch])
        info_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(info_table)
        story.append(Spacer(1, 15))

        # 3. Line Items Table
        table_rows = [
            [
                Paragraph("<b>Item Description</b>", bold_style),
                Paragraph("<b>Qty</b>", bold_style),
                Paragraph("<b>Unit Price (Rs.)</b>", right_bold),
                Paragraph("<b>Total (Rs.)</b>", right_bold),
            ]
        ]

        for item in bill.items:
            prod_name = item.product.name if item.product else "Product"
            unit_str = f" {item.product.unit}" if (item.product and item.product.unit) else ""
            table_rows.append(
                [
                    Paragraph(prod_name, normal_style),
                    Paragraph(f"{float(item.quantity):.1f}{unit_str}", normal_style),
                    Paragraph(f"{float(item.unit_price):.2f}", ParagraphStyle("r", parent=normal_style, alignment=2)),
                    Paragraph(f"{float(item.total_price):.2f}", ParagraphStyle("r2", parent=normal_style, alignment=2)),
                ]
            )

        items_table = Table(table_rows, colWidths=[3.2 * inch, 1.3 * inch, 1.5 * inch, 1.5 * inch])
        items_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                    ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#cbd5e1")),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ]
            )
        )
        story.append(items_table)
        story.append(Spacer(1, 15))

        # 4. Summary & Totals
        summary_rows = [
            ["Subtotal:", f"Rs. {float(bill.subtotal):.2f}"],
        ]
        if bill.discount_amount and bill.discount_amount > Decimal("0.00"):
            summary_rows.append(["Discount:", f"- Rs. {float(bill.discount_amount):.2f}"])
        if bill.tax_amount and bill.tax_amount > Decimal("0.00"):
            summary_rows.append(["Tax / GST:", f"+ Rs. {float(bill.tax_amount):.2f}"])

        summary_rows.append(["Total Amount:", f"Rs. {float(bill.total_amount):.2f}"])

        summary_table_data = []
        for label, val in summary_rows:
            is_grand = "Total Amount" in label
            f_label = Paragraph(f"<b>{label}</b>", bold_style) if is_grand else Paragraph(label, subtitle_style)
            f_val = (
                Paragraph(f"<b>{val}</b>", ParagraphStyle("g_val", parent=bold_style, fontSize=12, alignment=2))
                if is_grand
                else Paragraph(val, ParagraphStyle("s_val", parent=subtitle_style, alignment=2))
            )
            summary_table_data.append(["", "", f_label, f_val])

        summary_table = Table(summary_table_data, colWidths=[2.5 * inch, 2.0 * inch, 1.5 * inch, 1.5 * inch])
        summary_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                    ("LINEABOVE", (2, -1), (-1, -1), 1, colors.HexColor("#1e293b")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 30))

        # 5. Footer
        footer_p = Paragraph(
            "<i>Thank you for your business! Generated automatically by Business AI Robot.</i>",
            ParagraphStyle("foot", parent=subtitle_style, alignment=1),
        )
        story.append(footer_p)

        # Build document
        doc.build(story)
        return filepath
