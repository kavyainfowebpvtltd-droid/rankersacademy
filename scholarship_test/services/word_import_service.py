import posixpath
import re
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from django.conf import settings


DOCX_NAMESPACE = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'v': 'urn:schemas-microsoft-com:vml',
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
}
DOCX_REL_NAMESPACE = {
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}
BLOCK_MARKERS = {'question', 'type', 'option', 'answer', 'solution', 'marks'}
OPTION_LABELS = ('a', 'b', 'c', 'd')
SUBJECT_HEADINGS = {
    'PHYSICS',
    'CHEMISTRY',
    'BIOLOGY',
    'BOTANY',
    'ZOOLOGY',
    'MATHEMATICS',
    'MATHS',
}
QUESTION_TYPE_HEADINGS = {
    'MULTIPLE CHOICE QUESTIONS': 'mcq',
    'NUMERICAL TYPE QUESTIONS': 'int',
}

TYPE_MAP = {
    'multiple_choice': 'mcq',
    'multiple choice': 'mcq',
    'integer': 'int',
    'fill_ups': 'fitb',
    'fill ups': 'fitb',
    'fillups': 'fitb',
    'true_false': 'tf',
    'true false': 'tf',
    'comprehension': 'comp',
}

OPTION_PATTERN = re.compile(r'\(\s*([a-d])\s*\)', re.IGNORECASE)
QUESTION_NUMBER_PATTERN = re.compile(r'^\s*(?P<number>\d+)\s*[\.\)]\s*(?P<rest>.*)$')
ONLINE_TEST_QUESTION_LABEL_PATTERN = re.compile(r'^Q\s*(?P<number>\d+)\s*[\.\)]?\s*$', re.IGNORECASE)
ANSWER_LINE_PATTERN = re.compile(r'^answer\s*:\s*(?P<value>.*)$', re.IGNORECASE)


class WordImportError(ValueError):
    pass


def import_questions_from_docx(uploaded_file):
    archive, root = _open_docx(uploaded_file)
    try:
        plain_paragraphs = _extract_docx_paragraphs(root)
        if not plain_paragraphs:
            raise WordImportError("The Word file is empty or could not be read.")

        if _looks_like_marker_format(plain_paragraphs):
            questions, warnings = _parse_question_blocks(plain_paragraphs)
            if not questions:
                raise WordImportError("No questions matching the sample format were found.")

            section_name = Path(getattr(uploaded_file, 'name', 'Imported Questions')).stem.strip()
            return {
                'section_name': section_name or 'Imported Questions',
                'questions': questions,
                'warnings': warnings,
            }

        online_test = _parse_online_test_document(archive, root, uploaded_file)
        if online_test:
            return online_test

        imported_exam = _parse_exam_document(archive, root, uploaded_file)
        if imported_exam:
            return imported_exam

        raise WordImportError("No questions matching the sample format were found.")
    finally:
        archive.close()


def _open_docx(uploaded_file):
    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    try:
        archive = ZipFile(uploaded_file)
    except BadZipFile as exc:
        raise WordImportError("Only valid .docx Word files are supported.") from exc

    try:
        document_xml = archive.read('word/document.xml')
    except KeyError as exc:
        archive.close()
        raise WordImportError("The Word file is missing its document content.") from exc

    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        archive.close()
        raise WordImportError("The Word file could not be parsed.") from exc

    return archive, root


def _extract_docx_paragraphs(root):
    paragraphs = []
    body = root.find('./w:body', DOCX_NAMESPACE)
    if body is None:
        return paragraphs

    for para in body.findall('./w:p', DOCX_NAMESPACE):
        text_parts = []
        for text_node in para.findall('.//w:t', DOCX_NAMESPACE):
            text_parts.append(text_node.text or '')
        text = ''.join(text_parts).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _parse_online_test_document(archive, root, uploaded_file):
    body_items = _extract_docx_body_items(archive, root, uploaded_file)
    if not body_items:
        return None

    metadata = _extract_online_test_metadata(body_items, uploaded_file)
    questions, warnings = _parse_online_test_questions(body_items)
    if not questions:
        return None

    section_name = metadata['section_name']
    section = _build_section(section_name)
    section['questions'] = questions

    return {
        'section_name': section_name,
        'sections': [section],
        'questions': questions,
        'warnings': warnings,
        'test_name': metadata.get('test_name') or '',
        'duration_hours': metadata.get('duration_hours'),
        'duration_minutes': metadata.get('duration_minutes'),
    }


def _looks_like_marker_format(lines):
    normalized = [_normalize_marker(line) for line in lines[:80]]
    return 'question' in normalized and 'type' in normalized


def _parse_exam_document(archive, root, uploaded_file):
    blocks = _extract_docx_blocks(archive, root, uploaded_file)
    if not blocks:
        return None

    metadata = _extract_exam_metadata(blocks, uploaded_file)
    sections, warnings = _parse_exam_sections(blocks, metadata)

    sections = [section for section in sections if section.get('questions')]
    if not sections:
        return None

    return {
        'section_name': metadata['section_name'],
        'sections': sections,
        'questions': sections[0]['questions'] if len(sections) == 1 else [],
        'warnings': warnings,
        'test_name': metadata.get('test_name') or '',
        'duration_hours': metadata.get('duration_hours'),
        'duration_minutes': metadata.get('duration_minutes'),
    }


def _extract_docx_blocks(archive, root, uploaded_file):
    image_context = _build_image_context(archive, uploaded_file)
    blocks = []

    for para in root.findall('.//w:p', DOCX_NAMESPACE):
        parts = _extract_paragraph_parts(para, image_context)
        html = _render_parts_html(parts).strip()
        text = _normalize_block_text(_render_parts_text(parts))
        if html or text:
            blocks.append(
                {
                    'parts': parts,
                    'html': html,
                    'text': text,
                }
            )

    return blocks


def _extract_docx_body_items(archive, root, uploaded_file):
    body = root.find('./w:body', DOCX_NAMESPACE)
    if body is None:
        return []

    image_context = _build_image_context(archive, uploaded_file)
    items = []
    for child in list(body):
        tag = _local_name(child.tag)
        if tag == 'p':
            parts = _extract_paragraph_parts(child, image_context)
            html = _render_parts_html(parts).strip()
            text = _normalize_block_text(_render_parts_text(parts))
            items.append(
                {
                    'kind': 'paragraph',
                    'parts': parts,
                    'html': html,
                    'text': text,
                }
            )
        elif tag == 'tbl':
            texts = _extract_table_texts(child)
            items.append(
                {
                    'kind': 'table',
                    'texts': texts,
                    'text': _normalize_block_text(' '.join(texts)),
                }
            )

    return items


def _extract_table_texts(table):
    texts = []
    for cell in table.findall('.//w:tc', DOCX_NAMESPACE):
        cell_parts = []
        for para in cell.findall('./w:p', DOCX_NAMESPACE):
            paragraph_text = ''.join(
                text_node.text or ''
                for text_node in para.findall('.//w:t', DOCX_NAMESPACE)
            ).strip()
            if paragraph_text:
                cell_parts.append(paragraph_text)
        cell_text = _normalize_block_text(' '.join(cell_parts))
        if cell_text:
            texts.append(cell_text)
    return texts


def _build_image_context(archive, uploaded_file):
    relationships = {}
    try:
        rel_root = ET.fromstring(archive.read('word/_rels/document.xml.rels'))
    except (KeyError, ET.ParseError):
        rel_root = None

    if rel_root is not None:
        for rel in rel_root.findall('rel:Relationship', DOCX_REL_NAMESPACE):
            rel_id = rel.attrib.get('Id')
            target = rel.attrib.get('Target')
            if not rel_id or not target:
                continue
            normalized = posixpath.normpath(posixpath.join('word', target))
            relationships[rel_id] = normalized

    stem = _slugify(Path(getattr(uploaded_file, 'name', 'imported-test')).stem)
    session_name = f"{stem or 'imported-test'}-{uuid4().hex[:12]}"
    base_dir = Path(settings.MEDIA_ROOT) / 'word_imports' / session_name

    return {
        'archive': archive,
        'base_dir': base_dir,
        'relationships': relationships,
        'saved_urls': {},
        'session_name': session_name,
    }


def _extract_paragraph_parts(paragraph, image_context):
    parts = []
    _collect_parts(paragraph, image_context, parts, {'subscript': False, 'superscript': False})
    return _compact_parts(parts)


def _collect_parts(node, image_context, parts, text_style):
    tag = _local_name(node.tag)
    current_style = text_style

    if tag == 'r':
        current_style = _style_from_run(node)

    if tag == 't':
        value = node.text or ''
        if value:
            parts.append(
                {
                    'type': 'text',
                    'text': value,
                    'subscript': current_style.get('subscript', False),
                    'superscript': current_style.get('superscript', False),
                }
            )
    elif tag == 'tab':
        parts.append(
            {
                'type': 'text',
                'text': ' ',
                'subscript': current_style.get('subscript', False),
                'superscript': current_style.get('superscript', False),
            }
        )
    elif tag in {'br', 'cr'}:
        parts.append({'type': 'break'})
    elif tag == 'blip':
        rel_id = node.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
        image_html = _get_image_html(rel_id, image_context)
        if image_html:
            parts.append({'type': 'image', 'html': image_html})
    elif tag == 'imagedata':
        rel_id = node.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        image_html = _get_image_html(rel_id, image_context)
        if image_html:
            parts.append({'type': 'image', 'html': image_html})

    for child in list(node):
        _collect_parts(child, image_context, parts, current_style)


def _style_from_run(run):
    style = {'subscript': False, 'superscript': False}
    run_props = run.find('./w:rPr', DOCX_NAMESPACE)
    if run_props is None:
        return style

    vert_align = run_props.find('./w:vertAlign', DOCX_NAMESPACE)
    if vert_align is None:
        return style

    value = (vert_align.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val') or vert_align.attrib.get('w:val') or vert_align.attrib.get('val') or '').lower()
    if value == 'subscript':
        style['subscript'] = True
    elif value == 'superscript':
        style['superscript'] = True
    return style


def _get_image_html(rel_id, image_context):
    if not rel_id:
        return ''

    saved_urls = image_context['saved_urls']
    if rel_id in saved_urls:
        return _build_image_html(saved_urls[rel_id])

    target = image_context['relationships'].get(rel_id)
    if not target:
        return ''

    try:
        image_bytes = image_context['archive'].read(target)
    except KeyError:
        return ''

    suffix = Path(target).suffix or '.png'
    file_name = f"{rel_id}{suffix}"
    output_dir = image_context['base_dir']
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / file_name
    output_path.write_bytes(image_bytes)

    media_prefix = settings.MEDIA_URL.rstrip('/')
    url = f"{media_prefix}/word_imports/{image_context['session_name']}/{file_name}"
    saved_urls[rel_id] = url
    return _build_image_html(url)


def _build_image_html(url):
    return (
        '<img src="'
        + escape(url)
        + '" alt="Imported image" style="max-width:100%;height:auto;vertical-align:middle;">'
    )


def _compact_parts(parts):
    compacted = []
    for part in parts:
        if part['type'] == 'text' and not part.get('text'):
            continue
        if (
            compacted
            and part['type'] == 'text'
            and compacted[-1]['type'] == 'text'
            and compacted[-1].get('subscript') == part.get('subscript')
            and compacted[-1].get('superscript') == part.get('superscript')
        ):
            compacted[-1]['text'] += part['text']
        else:
            compacted.append(part)
    return compacted


def _render_parts_html(parts):
    html_parts = []
    for part in parts:
        if part['type'] == 'text':
            text = escape(part['text'])
            if part.get('subscript'):
                text = f'<sub>{text}</sub>'
            elif part.get('superscript'):
                text = f'<sup>{text}</sup>'
            html_parts.append(text)
        elif part['type'] == 'break':
            html_parts.append('<br>')
        elif part['type'] == 'image':
            html_parts.append(part['html'])
    return ''.join(html_parts)


def _render_parts_text(parts):
    text_parts = []
    for part in parts:
        if part['type'] == 'text':
            text_parts.append(part['text'])
        elif part['type'] == 'break':
            text_parts.append(' ')
    return ''.join(text_parts)


def _normalize_block_text(value):
    return ' '.join(str(value or '').replace('\xa0', ' ').split())


def _extract_exam_metadata(blocks, uploaded_file):
    fallback_name = Path(getattr(uploaded_file, 'name', 'Imported Questions')).stem.strip() or 'Imported Questions'
    metadata = {
        'section_name': fallback_name,
        'test_name': fallback_name,
        'duration_hours': None,
        'duration_minutes': None,
    }

    first_section_index = len(blocks)
    for idx, block in enumerate(blocks):
        if _is_subject_heading(block['text']):
            first_section_index = idx
            break

    header_blocks = blocks[:first_section_index]
    for block in header_blocks:
        text = block['text']
        if _looks_like_test_title(text):
            metadata['test_name'] = text
            metadata['section_name'] = text

        duration = _parse_duration(text)
        if duration is not None:
            metadata['duration_hours'], metadata['duration_minutes'] = duration

    return metadata


def _extract_online_test_metadata(body_items, uploaded_file):
    fallback_name = Path(getattr(uploaded_file, 'name', 'Imported Questions')).stem.strip() or 'Imported Questions'
    metadata = {
        'section_name': fallback_name,
        'test_name': fallback_name,
        'duration_hours': None,
        'duration_minutes': None,
    }

    for item in body_items:
        if item.get('kind') != 'paragraph':
            continue

        text = item.get('text', '')
        if not text:
            continue

        if _looks_like_test_title(text):
            metadata['test_name'] = text
            metadata['section_name'] = text

        duration = _parse_duration(text)
        if duration is not None:
            metadata['duration_hours'], metadata['duration_minutes'] = duration

    return metadata


def _parse_online_test_questions(body_items):
    questions = []
    warnings = []
    pending_paragraph = None
    current_question = None

    for item in body_items:
        if item.get('kind') == 'paragraph':
            if item.get('text'):
                if current_question is not None and not current_question.get('_stem_assigned'):
                    current_question['text'] = item.get('html', '').strip() or escape(item.get('text', ''))
                    current_question['_source_text'] = item.get('text', '').strip()
                    current_question['_stem_assigned'] = True
                    pending_paragraph = None
                else:
                    pending_paragraph = item
            continue

        for group_type, table_texts in _split_online_table_groups(item.get('texts') or []):
            if not table_texts:
                continue

            if group_type == 'question':
                question = _build_online_test_question(pending_paragraph, table_texts)
                questions.append(question)
                current_question = question
                pending_paragraph = None
                continue

            if current_question is None:
                continue

            if _table_contains_option_rows(table_texts):
                _apply_pending_online_stem(current_question)
                current_question['options'] = _parse_online_test_options(table_texts)

            if _table_contains_answer_line(table_texts):
                _apply_online_test_answer(current_question, table_texts)

    if not questions:
        return [], []

    for question in questions:
        if not question.get('options'):
            warnings.append(
                "Some imported questions did not include options. Review them before saving the test."
            )
            break

    if any(_question_needs_answer_review(question) for question in questions):
        warnings.append(
            "Some imported questions did not include a recognized answer key. Review answers before publishing the test."
        )

    return questions, warnings


def _is_online_test_question_table(table_texts):
    if not table_texts:
        return False
    return bool(ONLINE_TEST_QUESTION_LABEL_PATTERN.match(_normalize_space(table_texts[0])))


def _split_online_table_groups(table_texts):
    groups = []
    index = 0
    texts = [str(text or '') for text in table_texts if str(text or '').strip()]

    while index < len(texts):
        text = texts[index]
        normalized = _normalize_space(text)

        if ONLINE_TEST_QUESTION_LABEL_PATTERN.match(normalized):
            question_group = [text]
            index += 1
            while index < len(texts):
                next_text = texts[index]
                next_normalized = _normalize_space(next_text)
                if (
                    ONLINE_TEST_QUESTION_LABEL_PATTERN.match(next_normalized)
                    or _is_online_option_text(next_text)
                    or ANSWER_LINE_PATTERN.match(next_normalized)
                ):
                    break
                question_group.append(next_text)
                index += 1
            groups.append(('question', question_group))
            continue

        content_group = []
        while index < len(texts):
            next_normalized = _normalize_space(texts[index])
            if ONLINE_TEST_QUESTION_LABEL_PATTERN.match(next_normalized):
                break
            content_group.append(texts[index])
            index += 1

        if content_group:
            groups.append(('content', content_group))

    return groups


def _build_online_test_question(paragraph_item, table_texts):
    fallback_text = ' '.join(table_texts[1:]).strip() or ' '.join(table_texts).strip()
    question_html = escape(fallback_text)
    question_text = fallback_text
    pending_stem_html = ''
    pending_stem_text = ''

    if paragraph_item and not _is_online_metadata_text(paragraph_item.get('text', '')):
        pending_stem_html = paragraph_item.get('html', '').strip() or escape(paragraph_item.get('text', ''))
        pending_stem_text = paragraph_item.get('text', '').strip()

    return {
        'type': 'mcq',
        'text': question_html,
        'difficulty': 'Medium',
        'pos_marks': None,
        'neg_marks': None,
        'neg_unattempted': 0,
        'tags': [],
        'options': [],
        'correct_options': [],
        'multi_select': False,
        '_source_text': question_text,
        '_stem_assigned': False,
        '_pending_stem_html': pending_stem_html,
        '_pending_stem_text': pending_stem_text,
    }


def _is_online_metadata_text(value):
    text = _normalize_space(value)
    if not text:
        return True

    upper_text = text.upper()
    return (
        _looks_like_test_title(text)
        or 'SINGLE-CORRECT' in upper_text
        or 'MCQ' in upper_text
        or 'EACH QUESTION IS FOLLOWED' in upper_text
    )


def _apply_pending_online_stem(question):
    if not question or question.get('_stem_assigned'):
        return

    pending_html = question.get('_pending_stem_html', '').strip()
    pending_text = question.get('_pending_stem_text', '').strip()
    if not pending_html and not pending_text:
        return

    question['text'] = pending_html or escape(pending_text)
    question['_source_text'] = pending_text
    question['_stem_assigned'] = True


def _table_contains_option_rows(table_texts):
    return bool(_build_online_option_source(table_texts).strip())


def _parse_online_test_options(table_texts):
    joined = _build_online_option_source(table_texts)
    options = []
    for match in OPTION_PATTERN.finditer(joined):
        start = match.end()
        next_match = OPTION_PATTERN.search(joined, start)
        end = next_match.start() if next_match else len(joined)
        option_text = _normalize_space(joined[start:end])
        if option_text:
            options.append(option_text)
    return options


def _build_online_option_source(table_texts):
    segments = []
    for text in table_texts:
        raw_text = str(text or '')
        normalized = _normalize_space(raw_text)
        if not normalized:
            continue
        if ONLINE_TEST_QUESTION_LABEL_PATTERN.match(normalized):
            continue

        option_text = re.split(r'\banswer\s*:', raw_text, maxsplit=1, flags=re.IGNORECASE)[0]
        if _is_online_option_text(option_text):
            segments.append(option_text)

    return ' '.join(segments)


def _is_online_option_text(value):
    return bool(OPTION_PATTERN.search(str(value or '')))


def _table_contains_answer_line(table_texts):
    return any(ANSWER_LINE_PATTERN.match(_normalize_space(text)) for text in table_texts)


def _apply_online_test_answer(question, table_texts):
    if not question:
        return

    options = question.get('options') or []
    for text in table_texts:
        normalized = _normalize_space(text)
        match = ANSWER_LINE_PATTERN.match(normalized)
        if not match:
            continue

        answer_value = match.group('value').strip()
        option_label_match = OPTION_PATTERN.match(answer_value)
        if option_label_match:
            option_index = ord(option_label_match.group(1).lower()) - ord('a')
            if 0 <= option_index < len(options):
                question['correct_options'] = [option_index]
                return

        normalized_answer = _normalize_space(
            OPTION_PATTERN.sub('', answer_value, count=1)
        )
        if normalized_answer:
            for index, option_text in enumerate(options):
                if _normalize_space(option_text) == normalized_answer:
                    question['correct_options'] = [index]
                    return


def _looks_like_test_title(value):
    text = _normalize_space(value)
    if not text:
        return False

    upper_text = text.upper()
    if 'RANKERS ACADEMY' in upper_text:
        return False
    if upper_text.startswith('DATE'):
        return False
    if upper_text.startswith('TIME'):
        return False
    if upper_text.startswith('BATCH'):
        return False
    if 'SESSION' in upper_text and 'TEST' not in upper_text and 'EXAM' not in upper_text:
        return False

    return bool(
        re.search(r'\b(TEST|EXAM|MOCK)\b', text, re.IGNORECASE)
        or re.search(r'\bCLASS\s+TEST\b', text, re.IGNORECASE)
    )


def _parse_duration(value):
    text = str(value or '')

    hour_match = re.search(r'(\d+)\s*(?:hr|hrs|hour|hours)\b', text, re.IGNORECASE)
    minute_match = re.search(r'(\d+)\s*(?:min|mins|minute|minutes)\b', text, re.IGNORECASE)

    if not hour_match and not minute_match:
        return None

    hours = int(hour_match.group(1)) if hour_match else 0
    minutes = int(minute_match.group(1)) if minute_match else 0
    return hours, minutes


def _parse_exam_sections(blocks, metadata):
    section_name = metadata.get('section_name') or 'Imported Questions'
    sections = []
    warnings = []
    current_section = None
    current_question_type = 'mcq'
    needs_answer_review = False
    index = 0

    while index < len(blocks):
        block = blocks[index]
        text = block['text']

        if _is_subject_heading(text):
            current_section = _build_section(_format_subject_name(text))
            sections.append(current_section)
            current_question_type = 'mcq'
            index += 1
            continue

        heading_type = QUESTION_TYPE_HEADINGS.get(_normalize_space(text).upper())
        if heading_type:
            current_question_type = heading_type
            index += 1
            continue

        if QUESTION_NUMBER_PATTERN.match(text):
            if current_section is None:
                current_section = _build_section(section_name)
                sections.append(current_section)

            question, index = _parse_exam_question(blocks, index, current_question_type)
            current_section['questions'].append(question)
            needs_answer_review = needs_answer_review or _question_needs_answer_review(question)
            continue

        index += 1

    if needs_answer_review:
        warnings.append(
            "This exam-paper format does not contain an answer key, so imported questions were added without correct answers. Review answers before publishing the test."
        )

    return sections, warnings


def _build_section(name):
    return {
        'name': name,
        'allow_switching': True,
        'instructions': '',
        'questions': [],
    }


def _parse_exam_question(blocks, index, question_type):
    first_block = blocks[index]
    match = QUESTION_NUMBER_PATTERN.match(first_block['text'])
    prefix_length = len(match.group(0)) - len(match.group('rest'))

    question_blocks = [
        {
            'parts': _trim_text_prefix(first_block['parts'], prefix_length),
            'html': '',
            'text': '',
        }
    ]
    question_blocks[0]['html'] = _render_parts_html(question_blocks[0]['parts'])
    question_blocks[0]['text'] = _normalize_block_text(_render_parts_text(question_blocks[0]['parts']))

    index += 1
    while index < len(blocks):
        text = blocks[index]['text']
        if _is_subject_heading(text) or QUESTION_TYPE_HEADINGS.get(_normalize_space(text).upper()):
            break
        if QUESTION_NUMBER_PATTERN.match(text):
            break
        question_blocks.append(blocks[index])
        index += 1

    question = _build_exam_question_payload(question_blocks, question_type)
    return question, index


def _build_exam_question_payload(blocks, question_type):
    if question_type == 'int':
        return _build_exam_integer_question(blocks)
    return _build_exam_mcq_question(blocks)


def _build_exam_mcq_question(blocks):
    stem_parts = []
    option_parts = {label: [] for label in OPTION_LABELS}
    active_option = None

    for block in blocks:
        block_stem, block_options, active_option = _parse_mcq_block_parts(block['parts'], active_option)
        _append_parts_with_break(stem_parts, block_stem)
        for label in OPTION_LABELS:
            _append_parts_with_break(option_parts[label], block_options.get(label, []))

    options = []
    for label in OPTION_LABELS:
        rendered = _render_parts_html(option_parts[label]).strip()
        if rendered:
            options.append(rendered)

    return {
        'type': 'mcq',
        'text': _render_parts_html(stem_parts).strip(),
        'difficulty': 'Medium',
        'pos_marks': None,
        'neg_marks': None,
        'neg_unattempted': 0,
        'tags': [],
        'options': options,
        'correct_options': [],
        'multi_select': False,
    }


def _build_exam_integer_question(blocks):
    question_parts = []
    for block in blocks:
        _append_parts_with_break(question_parts, block['parts'])

    return {
        'type': 'int',
        'text': _render_parts_html(question_parts).strip(),
        'difficulty': 'Medium',
        'pos_marks': None,
        'neg_marks': None,
        'neg_unattempted': 0,
        'tags': [],
        'correct_answer': '',
    }


def _parse_mcq_block_parts(parts, active_option):
    stem_parts = []
    option_parts = {}
    current_target = active_option

    for part in parts:
        if part['type'] != 'text':
            _append_part_to_bucket(stem_parts, option_parts, current_target, part)
            continue

        for segment in _split_text_part_on_option_markers(part):
            if segment['type'] == 'marker':
                current_target = segment['label']
                option_parts.setdefault(current_target, [])
            else:
                _append_part_to_bucket(stem_parts, option_parts, current_target, segment['part'])

    return stem_parts, option_parts, current_target


def _append_part_to_bucket(stem_parts, option_parts, current_target, part):
    if current_target in OPTION_LABELS:
        option_parts.setdefault(current_target, []).append(part)
    else:
        stem_parts.append(part)


def _split_text_part_on_option_markers(part):
    segments = []
    value = part['text']
    cursor = 0

    for match in OPTION_PATTERN.finditer(value):
        if match.start() > cursor:
            segments.append(
                {
                    'type': 'content',
                    'part': _copy_text_part(part, value[cursor:match.start()]),
                }
            )
        segments.append({'type': 'marker', 'label': match.group(1).lower()})
        cursor = match.end()

    if cursor < len(value):
        segments.append(
            {
                'type': 'content',
                'part': _copy_text_part(part, value[cursor:]),
            }
        )

    if not segments:
        segments.append({'type': 'content', 'part': part})

    return segments


def _copy_text_part(part, text):
    return {
        'type': 'text',
        'text': text,
        'subscript': part.get('subscript', False),
        'superscript': part.get('superscript', False),
    }


def _append_parts_with_break(destination, new_parts):
    if not _parts_have_content(new_parts):
        return
    if _parts_have_content(destination):
        destination.append({'type': 'break'})
    destination.extend(new_parts)


def _parts_have_content(parts):
    for part in parts:
        if part['type'] == 'image':
            return True
        if part['type'] == 'text' and part.get('text', '').strip():
            return True
    return False


def _trim_text_prefix(parts, prefix_length):
    remaining = prefix_length
    trimmed = []

    for part in parts:
        if remaining <= 0:
            trimmed.append(part)
            continue

        if part['type'] != 'text':
            trimmed.append(part)
            continue

        text = part['text']
        if len(text) <= remaining:
            remaining -= len(text)
            continue

        trimmed.append(_copy_text_part(part, text[remaining:]))
        remaining = 0

    return _compact_parts(trimmed)


def _question_needs_answer_review(question):
    question_type = question.get('type')
    if question_type == 'mcq':
        return not question.get('correct_options')
    if question_type in {'tf', 'fitb', 'int'}:
        return not str(question.get('correct_answer', '')).strip()
    return False


def _is_subject_heading(value):
    return _normalize_space(value).upper() in SUBJECT_HEADINGS


def _format_subject_name(value):
    normalized = _normalize_space(value).upper()
    return normalized.title()


def _normalize_space(value):
    return ' '.join(str(value or '').split())


def _slugify(value):
    cleaned = re.sub(r'[^A-Za-z0-9]+', '-', str(value or '').strip()).strip('-').lower()
    return cleaned[:60]


def _local_name(tag):
    if '}' in tag:
        return tag.rsplit('}', 1)[-1]
    return tag


def _parse_question_blocks(lines):
    index = 0
    questions = []
    warnings = []

    while index < len(lines):
        marker = _normalize_marker(lines[index])
        if marker != 'question':
            index += 1
            continue

        question, index, question_warnings = _parse_single_question(lines, index)
        questions.append(question)
        warnings.extend(question_warnings)

    return questions, warnings


def _parse_single_question(lines, index):
    warnings = []

    index += 1
    question_lines, index = _collect_until_marker(lines, index)

    if index >= len(lines) or _normalize_marker(lines[index]) != 'type':
        raise WordImportError("Each question block must contain a Type field.")

    index += 1
    type_lines, index = _collect_until_marker(lines, index)
    raw_type = ' '.join(type_lines).strip()
    question_type = TYPE_MAP.get(_normalize_type(raw_type))
    if not question_type:
        raise WordImportError(f"Unsupported question type: {raw_type or 'blank'}.")

    if question_type == 'mcq':
        question, index = _parse_multiple_choice(lines, index, question_lines)
    elif question_type == 'fitb':
        question, index = _parse_fill_ups(lines, index, question_lines)
    elif question_type == 'tf':
        question, index = _parse_answer_question(lines, index, question_lines, 'tf')
    elif question_type == 'int':
        question, index = _parse_answer_question(lines, index, question_lines, 'int')
    elif question_type == 'comp':
        question, index, comp_warnings = _parse_comprehension(lines, index, question_lines)
        warnings.extend(comp_warnings)
    else:
        raise WordImportError(f"Unsupported question type: {raw_type or 'blank'}.")

    return question, index, warnings


def _parse_multiple_choice(lines, index, question_lines):
    options = []
    correct_indexes = []

    while index < len(lines) and _normalize_marker(lines[index]) == 'option':
        index += 1
        option_lines, index = _collect_until_marker(lines, index)
        if not option_lines:
            continue

        option_text, status = _split_option_text_and_status(option_lines)

        options.append(option_text)
        if status == 'correct':
            correct_indexes.append(len(options) - 1)

    _, index = _consume_optional_solution(lines, index)
    pos_marks, neg_marks, index = _consume_marks(lines, index)

    return (
        {
            'type': 'mcq',
            'text': _lines_to_html(question_lines),
            'difficulty': 'Medium',
            'pos_marks': pos_marks,
            'neg_marks': neg_marks,
            'neg_unattempted': 0,
            'tags': [],
            'options': options,
            'correct_options': correct_indexes,
            'multi_select': len(correct_indexes) > 1,
        },
        index,
    )


def _parse_fill_ups(lines, index, question_lines):
    accepted_answers = []

    while index < len(lines) and _normalize_marker(lines[index]) == 'option':
        index += 1
        option_lines, index = _collect_until_marker(lines, index)
        answer_value = '\n'.join(option_lines).strip()
        if answer_value:
            accepted_answers.append(answer_value)

    _, index = _consume_optional_solution(lines, index)
    pos_marks, neg_marks, index = _consume_marks(lines, index)

    return (
        {
            'type': 'fitb',
            'text': _lines_to_html(question_lines),
            'difficulty': 'Medium',
            'pos_marks': pos_marks,
            'neg_marks': neg_marks,
            'neg_unattempted': 0,
            'tags': [],
            'correct_answer': ' | '.join(accepted_answers),
        },
        index,
    )


def _parse_answer_question(lines, index, question_lines, question_type):
    answer_value = ''

    if index < len(lines) and _normalize_marker(lines[index]) == 'answer':
        index += 1
        answer_lines, index = _collect_until_marker(lines, index)
        answer_value = '\n'.join(answer_lines).strip()

    _, index = _consume_optional_solution(lines, index)
    pos_marks, neg_marks, index = _consume_marks(lines, index)

    return (
        {
            'type': question_type,
            'text': _lines_to_html(question_lines),
            'difficulty': 'Medium',
            'pos_marks': pos_marks,
            'neg_marks': neg_marks,
            'neg_unattempted': 0,
            'tags': [],
            'correct_answer': answer_value,
        },
        index,
    )


def _parse_comprehension(lines, index, question_lines):
    warnings = []
    nested_questions = []

    while index < len(lines):
        marker = _normalize_marker(lines[index])
        if marker != 'question':
            break

        nested_question, index, nested_warnings = _parse_single_question(lines, index)
        nested_questions.append(_format_comprehension_subquestion(nested_question, len(nested_questions) + 1))
        warnings.extend(nested_warnings)

    title = question_lines[0] if question_lines else 'Comprehension'
    passage_lines = question_lines[1:] if len(question_lines) > 1 else question_lines

    if not nested_questions:
        warnings.append("A comprehension passage was found without any nested questions.")

    return (
        {
            'type': 'comp',
            'text': _lines_to_html([title]),
            'difficulty': 'Medium',
            'pos_marks': 0,
            'neg_marks': 0,
            'neg_unattempted': 0,
            'tags': [],
            'passage': _lines_to_html(passage_lines),
            'sub_questions': nested_questions,
        },
        index,
        warnings,
    )


def _format_comprehension_subquestion(question, number):
    type_label = {
        'mcq': 'Multiple Choice',
        'fitb': 'Fill In The Blanks',
        'tf': 'True / False',
        'int': 'Integer',
        'comp': 'Comprehension',
    }.get(question.get('type'), 'Question')

    parts = [f"{number}. [{type_label}] {_html_to_text(question.get('text', ''))}"]

    if question.get('type') == 'mcq':
        options = question.get('options', [])
        correct_indexes = set(question.get('correct_options', []))
        for option_index, option_text in enumerate(options):
            marker = ' (Correct)' if option_index in correct_indexes else ''
            parts.append(f"Option {option_index + 1}: {option_text}{marker}")
    elif question.get('correct_answer'):
        parts.append(f"Answer: {question.get('correct_answer')}")

    parts.append(
        f"Marks: +{question.get('pos_marks', 0)} / -{question.get('neg_marks', 0)}"
    )
    return '\n'.join(parts)


def _consume_optional_solution(lines, index):
    if index < len(lines) and _normalize_marker(lines[index]) == 'solution':
        index += 1
        return _collect_until_marker(lines, index)
    return [], index


def _consume_marks(lines, index):
    if index >= len(lines) or _normalize_marker(lines[index]) != 'marks':
        return 0, 0, index

    index += 1
    mark_lines, index = _collect_until_marker(lines, index)
    pos_marks = _to_number(mark_lines[0]) if len(mark_lines) >= 1 else 0
    neg_marks = _to_number(mark_lines[1]) if len(mark_lines) >= 2 else 0
    return pos_marks, neg_marks, index


def _collect_until_marker(lines, index):
    collected = []
    while index < len(lines) and _normalize_marker(lines[index]) not in BLOCK_MARKERS:
        collected.append(lines[index].strip())
        index += 1
    return collected, index


def _normalize_marker(value):
    return str(value or '').strip().lower()


def _normalize_type(value):
    return str(value or '').strip().lower().replace('-', '_')


def _normalize_status(value):
    normalized = str(value or '').strip().lower()
    normalized = re.sub(r'[\s\.\,\:\;\-\–\—\(\)\[\]\{\}]+$', '', normalized)
    return normalized


def _split_option_text_and_status(option_lines):
    cleaned_lines = [str(line).strip() for line in option_lines if str(line).strip()]
    if not cleaned_lines:
        return '', 'incorrect'

    status = _normalize_status(cleaned_lines[-1])
    if status in {'correct', 'incorrect'}:
        return '\n'.join(cleaned_lines[:-1]).strip(), status

    return '\n'.join(cleaned_lines).strip(), 'incorrect'


def _to_number(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _lines_to_html(lines):
    cleaned_lines = [escape(str(line).strip()) for line in lines if str(line).strip()]
    return '<br>'.join(cleaned_lines)


def _html_to_text(value):
    return (
        str(value or '')
        .replace('<br>', '\n')
        .replace('<br/>', '\n')
        .replace('<br />', '\n')
    )
