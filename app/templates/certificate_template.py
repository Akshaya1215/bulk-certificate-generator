import io
import uuid
from datetime import date
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from app.exceptions.custom_exceptions import CertificateGenerationError


class CertificateTemplate:
    """Predefined professional certificate template using ReportLab."""

    PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)

    # Palette
    COLOR_PRIMARY = colors.HexColor("#1E3A8A")     # Deep Classic Navy
    COLOR_SECONDARY = colors.HexColor("#B45309")   # Warm Gold
    COLOR_TEXT_MAIN = colors.HexColor("#0F172A")   # Slate Dark
    COLOR_TEXT_MUTED = colors.HexColor("#64748B")  # Slate Muted
    COLOR_BORDER_OUTER = colors.HexColor("#1E3A8A")
    COLOR_BORDER_INNER = colors.HexColor("#D97706")

    @classmethod
    def _fit_font_size(
        cls,
        c: canvas.Canvas,
        text: str,
        font_name: str,
        max_size: float,
        min_size: float,
        max_allowed_width: float,
    ) -> float:
        """Dynamically computes the optimal font size fitting within max_allowed_width using ReportLab stringWidth."""
        size = float(max_size)
        while size > min_size:
            rendered_width = c.stringWidth(text, font_name, size)
            if rendered_width <= max_allowed_width:
                break
            size -= 1.0
        return max(size, min_size)

    @classmethod
    def generate_pdf_bytes(
        cls,
        certificate_id: uuid.UUID | str,
        recipient_name: str,
        event_name: str,
        completion_date: date | str,
    ) -> bytes:
        """Renders the predefined certificate template into PDF bytes with dynamic text fitting."""
        try:
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=landscape(A4))

            width, height = cls.PAGE_WIDTH, cls.PAGE_HEIGHT
            max_text_width = width - 140  # Keep safe padding from inner borders

            # 1. Background fill
            c.setFillColor(colors.HexColor("#F8FAFC"))
            c.rect(0, 0, width, height, stroke=0, fill=1)

            # 2. Decorative Double Border
            margin_outer = 25
            c.setStrokeColor(cls.COLOR_BORDER_OUTER)
            c.setLineWidth(3)
            c.rect(margin_outer, margin_outer, width - 2 * margin_outer, height - 2 * margin_outer, stroke=1, fill=0)

            margin_inner = 32
            c.setStrokeColor(cls.COLOR_BORDER_INNER)
            c.setLineWidth(1)
            c.rect(margin_inner, margin_inner, width - 2 * margin_inner, height - 2 * margin_inner, stroke=1, fill=0)

            # 3. Corner Ornaments (Geometric corner accents)
            corner_size = 20
            for x, y, dx, dy in [
                (margin_inner, margin_inner, corner_size, corner_size),
                (width - margin_inner, margin_inner, -corner_size, corner_size),
                (margin_inner, height - margin_inner, corner_size, -corner_size),
                (width - margin_inner, height - margin_inner, -corner_size, -corner_size),
            ]:
                c.setStrokeColor(cls.COLOR_SECONDARY)
                c.setLineWidth(2)
                c.line(x, y, x + dx, y)
                c.line(x, y, x, y + dy)

            # 4. Top Accent Ribbon
            c.setFillColor(cls.COLOR_PRIMARY)
            c.rect(margin_inner, height - margin_inner - 12, width - 2 * margin_inner, 12, stroke=0, fill=1)
            c.setFillColor(cls.COLOR_SECONDARY)
            c.rect(margin_inner, height - margin_inner - 16, width - 2 * margin_inner, 4, stroke=0, fill=1)

            # 5. Header: Certificate Title
            c.setFillColor(cls.COLOR_PRIMARY)
            c.setFont("Helvetica-Bold", 32)
            c.drawCentredString(width / 2.0, height - 105, "CERTIFICATE OF COMPLETION")

            # Decorative divider under title
            c.setStrokeColor(cls.COLOR_SECONDARY)
            c.setLineWidth(1.5)
            c.line(width / 2.0 - 120, height - 118, width / 2.0 + 120, height - 118)

            # 6. Presentation text
            c.setFillColor(cls.COLOR_TEXT_MUTED)
            c.setFont("Helvetica", 13)
            c.drawCentredString(width / 2.0, height - 155, "PROUDLY PRESENTED TO")

            # 7. Recipient Name with dynamic text fitting
            clean_name = str(recipient_name).strip()
            name_font_size = cls._fit_font_size(
                c, clean_name, "Helvetica-Bold", max_size=28, min_size=14, max_allowed_width=max_text_width
            )
            c.setFillColor(cls.COLOR_TEXT_MAIN)
            c.setFont("Helvetica-Bold", name_font_size)
            c.drawCentredString(width / 2.0, height - 200, clean_name)

            # Underline dynamically proportioned to rendered name width
            rendered_name_width = min(c.stringWidth(clean_name, "Helvetica-Bold", name_font_size), max_text_width)
            underline_half = max(rendered_name_width / 2.0 + 15, 60)
            c.setStrokeColor(cls.COLOR_PRIMARY)
            c.setLineWidth(1)
            c.line(width / 2.0 - underline_half, height - 212, width / 2.0 + underline_half, height - 212)

            # 8. Description statement
            c.setFillColor(cls.COLOR_TEXT_MUTED)
            c.setFont("Helvetica", 13)
            c.drawCentredString(width / 2.0, height - 250, "for successfully completing the course/program")

            # 9. Event / Course Name with dynamic text fitting
            clean_event = f'"{event_name.strip()}"'
            event_font_size = cls._fit_font_size(
                c, clean_event, "Helvetica-Bold", max_size=22, min_size=12, max_allowed_width=max_text_width
            )
            c.setFillColor(cls.COLOR_PRIMARY)
            c.setFont("Helvetica-Bold", event_font_size)
            c.drawCentredString(width / 2.0, height - 290, clean_event)

            # 10. Metadata Section (Date, Certificate ID, Signature)
            meta_y = 100

            # Left: Date
            date_str = completion_date.isoformat() if isinstance(completion_date, date) else str(completion_date)
            c.setFillColor(cls.COLOR_TEXT_MUTED)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(70, meta_y + 25, "DATE OF ISSUANCE")
            c.setFillColor(cls.COLOR_TEXT_MAIN)
            c.setFont("Helvetica", 11)
            c.drawString(70, meta_y + 8, date_str)
            c.setStrokeColor(cls.COLOR_TEXT_MUTED)
            c.setLineWidth(0.5)
            c.line(70, meta_y, 220, meta_y)

            # Center: Certificate ID
            c.setFillColor(cls.COLOR_TEXT_MUTED)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(width / 2.0, meta_y + 25, "CERTIFICATE ID")
            c.setFillColor(cls.COLOR_TEXT_MAIN)
            c.setFont("Helvetica", 9)
            c.drawCentredString(width / 2.0, meta_y + 8, str(certificate_id))
            c.setStrokeColor(cls.COLOR_TEXT_MUTED)
            c.setLineWidth(0.5)
            c.line(width / 2.0 - 120, meta_y, width / 2.0 + 120, meta_y)

            # Right: Signature
            sig_x = width - 220
            c.setFillColor(cls.COLOR_PRIMARY)
            c.setFont("Helvetica-Oblique", 14)
            c.drawString(sig_x + 10, meta_y + 25, "Authorized Signatory")
            c.setStrokeColor(cls.COLOR_TEXT_MUTED)
            c.setLineWidth(0.5)
            c.line(sig_x, meta_y, width - 70, meta_y)
            c.setFillColor(cls.COLOR_TEXT_MUTED)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(sig_x, meta_y - 15, "AUTHORIZED SIGNATURE")

            # 11. Finalize canvas
            c.showPage()
            c.save()

            buffer.seek(0)
            return buffer.getvalue()
        except Exception as e:
            raise CertificateGenerationError(f"Failed to render certificate PDF: {e}") from e
