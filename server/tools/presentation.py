"""Render tool facts from Python results, never from a model's replacement text."""
import re


def _language(question):
    if re.search(r"[\u0590-\u05ff]", question):
        return "he"
    if re.search(r"[\u0600-\u06ff]", question):
        return "ar"
    return "en"


def render_tool_answer(tool_name, outputs, question):
    language = _language(question)
    if not outputs:
        if tool_name == "grade_calculator":
            return {
                "en": "The calculator was not executed. Please provide each component's grade and percentage weight, or retry if you already supplied them.",
                "ar": "لم تُنفّذ الحاسبة. أرسل درجة ووزن كل مكوّن بالنسبة المئوية، أو أعد المحاولة إذا أرسلتها بالفعل.",
                "he": "המחשבון לא הופעל. יש לציין את הציון והמשקל באחוזים של כל רכיב, או לנסות שוב אם הפרטים כבר נמסרו.",
            }[language]
        return {
            "en": "The course lookup was not executed. Please specify the course item to look up, or retry if you already supplied it.",
            "ar": "لم يُنفّذ البحث في معلومات المساق. حدد المهمة أو الامتحان المطلوب، أو أعد المحاولة إذا حددته بالفعل.",
            "he": "החיפוש במידע הקורס לא הופעל. יש לציין את המטלה או המבחן המבוקשים, או לנסות שוב.",
        }[language]

    paragraphs = []
    for output in outputs:
        if output["status"] == "error":
            prefix = {"en": "Tool request failed", "ar": "فشل طلب الأداة", "he": "בקשת הכלי נכשלה"}[language]
            paragraphs.append(f"{prefix}: {output['error']}")
            continue
        result = output["result"]
        if tool_name == "grade_calculator":
            label = {"en": "Final grade", "ar": "العلامة النهائية", "he": "ציון סופי"}[language]
            lines = [f"{label}: {result['final_grade']:g}"]
            for item in result["breakdown"]:
                lines.append(f"{item['name']}: {item['grade']:g} × {item['weight']:g}% = {item['weighted_value']:g}")
            paragraphs.append("\n".join(lines))
        elif not result["available"]:
            paragraphs.append({
                "en": "Verified information for this course item is not available. Check the official syllabus or course portal.",
                "ar": "لا تتوفر معلومات موثقة لهذا البند. راجع المنهاج الرسمي أو موقع المساق.",
                "he": "אין מידע מאומת עבור הפריט הזה. יש לבדוק בסילבוס הרשמי או באתר הקורס.",
            }[language])
        else:
            # Present verified records verbatim as data; no generative date/weight synthesis.
            lines = []
            for record in result["results"]:
                lines.append(record["name"])
                for field, value in record.items():
                    if field not in {"name", "aliases", "verified", "type"} and value is not None:
                        lines.append(f"{field}: {value}")
            paragraphs.append("\n".join(lines))
    return "\n\n".join(paragraphs)
