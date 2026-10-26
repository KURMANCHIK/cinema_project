from io import BytesIO
from pathlib import Path

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"

if FONT not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont(FONT, str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))

ACCENT = colors.HexColor("#e5484d")
TEXT = ParagraphStyle("text", fontName=FONT, fontSize=10.5, leading=15)
SMALL = ParagraphStyle("small", parent=TEXT, fontSize=8.5, leading=11, textColor=colors.grey)
TITLE = ParagraphStyle("title", fontName=FONT_BOLD, fontSize=20, leading=25, spaceAfter=4)
SUBTITLE = ParagraphStyle("subtitle", parent=TEXT, fontSize=11, textColor=colors.HexColor("#555555"))
HEADING = ParagraphStyle("heading", fontName=FONT_BOLD, fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=6)
CENTER = ParagraphStyle("center", parent=TEXT, alignment=TA_CENTER)


def _table(rows, widths, header=False):
    table = Table(rows, colWidths=widths)
    style = [
        ("FONT", (0, 0), (-1, -1), FONT, 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
    ]
    if header:
        style += [
            ("FONT", (0, 0), (-1, 0), FONT_BOLD, 10),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
        ]
    else:
        style += [("FONT", (0, 0), (0, -1), FONT_BOLD, 10), ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444"))]
    table.setStyle(TableStyle(style))
    return table


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.grey)
    stamp = timezone.localtime().strftime("%d.%m.%Y %H:%M")
    canvas.drawString(20 * mm, 12 * mm, f"Cinema · документ сформирован {stamp}")
    canvas.drawRightString(190 * mm, 12 * mm, f"стр. {doc.page}")
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(2)
    canvas.line(20 * mm, 285 * mm, 190 * mm, 285 * mm)
    canvas.restoreState()


def _build(story):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
        title="Cinema", author="Cinema",
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _movie_story(movie):
    story = [Paragraph(movie.title, TITLE)]
    if movie.original_title:
        story.append(Paragraph(f"{movie.original_title}, {movie.release_year}", SUBTITLE))
    story.append(Spacer(1, 6 * mm))
    rating = movie.average_rating()
    directors = ", ".join(person.full_name for person in movie.directors()) or "—"
    facts = [
        ["Жанр", movie.category.name if movie.category else "—"],
        ["Страны", ", ".join(country.name for country in movie.countries.all()) or "—"],
        ["Год выпуска", str(movie.release_year)],
        ["Премьера на сайте", movie.premiere_date.strftime("%d.%m.%Y") if movie.premiere_date else "—"],
        ["Длительность", movie.formatted_duration],
        ["Возраст", movie.age_rating],
        ["Доступ", movie.get_access_display()],
        ["Режиссёр", directors],
        ["Рейтинг зрителей", f"{rating:.1f} / 10" if rating else "нет оценок"],
        ["Просмотров", str(movie.views_count)],
    ]
    facts_table = _table([[k, Paragraph(v, TEXT)] for k, v in facts], [45 * mm, 70 * mm])
    if movie.poster:
        try:
            poster = Image(movie.poster.path, width=48 * mm, height=72 * mm)
            story.append(Table([[poster, facts_table]], colWidths=[55 * mm, 115 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]))
        except (OSError, ValueError):
            story.append(facts_table)
    else:
        story.append(facts_table)
    story += [Paragraph("Описание", HEADING), Paragraph(movie.description, TEXT)]
    credits = list(movie.credits.select_related("person"))
    if credits:
        rows = [["Персона", "Роль", "Персонаж"]] + [
            [credit.person.full_name, credit.get_role_display(), credit.character_name or "—"] for credit in credits
        ]
        story += [Paragraph("Съёмочная группа", HEADING), _table(rows, [65 * mm, 40 * mm, 65 * mm], header=True)]
    return story


def movie_card_pdf(movies):
    story = []
    for index, movie in enumerate(movies):
        if index:
            story.append(PageBreak())
        story += _movie_story(movie)
    return _build(story)


def subscription_receipt_pdf(subscription):
    started = timezone.localtime(subscription.started_at)
    expires = timezone.localtime(subscription.expires_at)
    user = subscription.user
    rows = [
        ["Номер документа", f"CIN-{subscription.pk:06d}"],
        ["Покупатель", user.get_full_name() or user.username],
        ["Email", user.email or "—"],
        ["Тариф", subscription.plan.name],
        ["Срок действия", f"{subscription.plan.duration_days} дн."],
        ["Начало", started.strftime("%d.%m.%Y %H:%M")],
        ["Окончание", expires.strftime("%d.%m.%Y %H:%M")],
        ["Статус", "активна" if subscription.is_active else "истекла"],
        ["Сумма", f"{subscription.price_paid:.2f} ₽"],
    ]
    story = [
        Paragraph("Квитанция об оплате подписки", TITLE),
        Paragraph("Онлайн-кинотеатр Cinema", SUBTITLE),
        Spacer(1, 8 * mm),
        _table(rows, [55 * mm, 115 * mm]),
        Spacer(1, 10 * mm),
        Paragraph("Спасибо, что выбираете Cinema! Подписка открывает доступ ко всем фильмам с отметкой «По подписке».", TEXT),
        Spacer(1, 4 * mm),
        Paragraph("Документ сформирован автоматически и не требует подписи.", SMALL),
    ]
    return _build(story)
