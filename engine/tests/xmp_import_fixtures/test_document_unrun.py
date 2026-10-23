"""AUTHORED / UNRUN: bounded XMP document and immutable source-read contract.

No product import, parser invocation, test execution, build or inference was
performed while authoring these fixtures. They require a security-patched Expat
runtime and must not be represented as passing/security certification.
"""
import hashlib
import os
from pathlib import Path

import pytest

from lumaretouch_engine import xmp_document as X


RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"
DC = "http://purl.org/dc/elements/1.1/"


def packet(body="", attributes="", *, prefix="crs", about=""):
    return (f'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
            f'<rdf:RDF xmlns:rdf="{RDF}">'
            f'<rdf:Description rdf:about="{about}" xmlns:{prefix}="{CRS}" '
            f'xmlns:dc="{DC}" {attributes}>{body}</rdf:Description>'
            '</rdf:RDF></x:xmpmeta>').encode("utf-8")


def assert_error(raw, code):
    with pytest.raises(X.XmpDocumentError) as caught:
        X.parse(raw)
    assert caught.value.code == code


def test_attribute_and_element_properties_are_sorted_without_numeric_mapping():
    raw = packet('<crs:Exposure2012> +0.25 </crs:Exposure2012>',
                 'crs:ProcessVersion="11.0" crs:Contrast2012="12"')
    doc = X.parse(raw, basename="portrait.xmp")
    assert doc["properties"] == {
        "Contrast2012": "12", "Exposure2012": " +0.25 ", "ProcessVersion": "11.0"}
    assert list(doc["properties"]) == sorted(doc["properties"])
    assert doc["raw"] is raw
    assert doc["sha256"] == hashlib.sha256(raw).hexdigest()
    assert doc["basename"] == "portrait.xmp"
    assert doc["metadata"]["byte_length"] == len(raw)


def test_namespace_uri_not_crs_prefix_controls_camera_raw_property_selection():
    raw = (f'<rdf:RDF xmlns:rdf="{RDF}"><rdf:Description '
           f'xmlns:a="{CRS}" xmlns:crs="https://attacker.invalid/" '
           'a:Exposure2012="1" crs:Exposure2012="999"/></rdf:RDF>').encode()
    doc = X.parse(raw)
    assert doc["properties"] == {"Exposure2012": "1"}
    assert doc["metadata"]["other_properties"] == {
        "{https://attacker.invalid/}Exposure2012": "999"}


def test_camera_raw_namespace_lookalikes_are_reported_not_imported():
    for namespace in (CRS.rstrip("/"), CRS.upper(), CRS + "extra", "urn:crs"):
        raw = packet(attributes='crs:Exposure2012="5"').replace(CRS.encode(), namespace.encode())
        doc = X.parse(raw)
        assert doc["properties"] == {}
        assert list(doc["metadata"]["other_properties"].values()) == ["5"]


def test_prefix_aliases_produce_same_properties_and_metadata_names():
    first = X.parse(packet('<crs:Contrast2012>2</crs:Contrast2012>'))
    second = X.parse(packet('<setting:Contrast2012>2</setting:Contrast2012>', prefix="setting"))
    assert first["properties"] == second["properties"]
    assert first["metadata"]["property_forms"] == second["metadata"]["property_forms"]
    assert first["sha256"] != second["sha256"]


def test_rdf_point_sequences_remain_ordered_plain_strings():
    raw = packet('<crs:ToneCurvePV2012><rdf:Seq>'
                 '<rdf:li>0, 0</rdf:li><rdf:li>128, 140</rdf:li><rdf:li>255, 255</rdf:li>'
                 '</rdf:Seq></crs:ToneCurvePV2012>')
    doc = X.parse(raw)
    assert doc["properties"]["ToneCurvePV2012"] == ["0, 0", "128, 140", "255, 255"]
    assert doc["metadata"]["property_forms"][f"{{{CRS}}}ToneCurvePV2012"] == {
        "source": "element", "container": "Seq"}


def test_unordered_rdf_bag_is_never_presented_as_an_ordered_curve_sequence():
    raw = packet('<crs:ToneCurvePV2012><rdf:Bag>'
                 '<rdf:li>0, 0</rdf:li><rdf:li>255, 255</rdf:li>'
                 '</rdf:Bag></crs:ToneCurvePV2012>')
    assert X.parse(raw)["properties"]["ToneCurvePV2012"] == {
        "kind": "array", "container": "Bag", "items": ["0, 0", "255, 255"]}


def test_unsupported_structures_remain_bounded_explicit_reports():
    raw = packet('<crs:Masks><rdf:Seq><rdf:li rdf:parseType="Resource">'
                 '<crs:Name>Mask A</crs:Name><crs:Unknown>future</crs:Unknown>'
                 '</rdf:li></rdf:Seq></crs:Masks>')
    assert X.parse(raw)["properties"]["Masks"] == {
        "kind": "array", "container": "Seq", "items": [
            {"kind": "structure", "fields": {
                f"{{{CRS}}}Name": "Mask A", f"{{{CRS}}}Unknown": "future"}}]}


def test_nested_description_and_abbreviated_structures_are_reported():
    raw = packet('<crs:One><rdf:Description crs:A="1"><crs:B>2</crs:B>'
                 '</rdf:Description></crs:One><crs:Two crs:C="3"/>')
    doc = X.parse(raw)
    assert doc["properties"]["One"] == {
        "kind": "structure", "fields": {f"{{{CRS}}}A": "1", f"{{{CRS}}}B": "2"}}
    assert doc["properties"]["Two"] == {
        "kind": "structure", "fields": {f"{{{CRS}}}C": "3"}}


def test_qualified_values_are_never_flattened_into_mapping_candidates():
    raw = packet('<crs:Future rdf:parseType="Resource"><rdf:value>12</rdf:value>'
                 '<dc:format>custom-unit</dc:format></crs:Future>')
    assert X.parse(raw)["properties"]["Future"] == {
        "kind": "qualified", "value": "12", "qualifiers": {f"{{{DC}}}format": "custom-unit"}}


def test_language_alt_metadata_and_standard_xml_escapes_are_retained():
    raw = packet('<dc:title><rdf:Alt><rdf:li xml:lang="x-default">A &amp; B</rdf:li>'
                 '<rdf:li xml:lang="zh-CN">人像</rdf:li></rdf:Alt></dc:title>',
                 'crs:Name="A &quot;quote&quot; &#38; B"')
    doc = X.parse(raw)
    assert doc["properties"]["Name"] == 'A "quote" & B'
    assert doc["metadata"]["other_properties"][f"{{{DC}}}title"] == {
        "kind": "array", "container": "Alt", "items": [
            {"kind": "literal", "value": "A & B", "language": "x-default"},
            {"kind": "literal", "value": "人像", "language": "zh-CN"}]}


def test_xml_language_reset_leaves_a_plain_scalar():
    raw = packet('<crs:Exposure2012 xml:lang="">1</crs:Exposure2012>', 'xml:lang="en"')
    assert X.parse(raw)["properties"] == {"Exposure2012": "1"}


def test_resource_uri_is_an_inert_report_without_file_or_network_resolution(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Parser attempted filesystem access")
    monkeypatch.setattr(os, "open", denied)
    raw = packet('<crs:Profile rdf:resource="file:///etc/passwd"/>')
    assert X.parse(raw)["properties"] == {
        "Profile": {"kind": "resource", "uri": "file:///etc/passwd"}}


@pytest.mark.parametrize("body,attributes", [
    ('<crs:Exposure2012>1</crs:Exposure2012>', 'crs:Exposure2012="1"'),
    ('<crs:Exposure2012>1</crs:Exposure2012><crs:Exposure2012>2</crs:Exposure2012>', ''),
    ('<crs:Future rdf:parseType="Resource"><crs:A>1</crs:A><crs:A>1</crs:A></crs:Future>', ''),
])
def test_duplicate_or_conflicting_properties_are_rejected_even_when_equal(body, attributes):
    assert_error(packet(body, attributes), "duplicate_property")


def test_duplicate_properties_across_descriptions_are_rejected():
    raw = (f'<rdf:RDF xmlns:rdf="{RDF}" xmlns:a="{CRS}" xmlns:b="{CRS}">'
           '<rdf:Description rdf:about="" a:Exposure2012="1"/>'
           '<rdf:Description rdf:about="" b:Exposure2012="1"/></rdf:RDF>').encode()
    assert_error(raw, "duplicate_property")


def test_distinct_properties_for_one_subject_merge_but_multiple_subjects_do_not():
    raw = (f'<rdf:RDF xmlns:rdf="{RDF}" xmlns:crs="{CRS}">'
           '<rdf:Description rdf:about="photo" crs:A="1"/>'
           '<rdf:Description rdf:about="photo" crs:B="2"/></rdf:RDF>').encode()
    doc = X.parse(raw)
    assert doc["properties"] == {"A": "1", "B": "2"}
    assert doc["metadata"]["subjects"] == ["photo"]
    assert doc["metadata"]["description_count"] == 2
    assert_error(raw.replace(b'about="photo"', b'about="other"', 1), "invalid_rdf")


def test_duplicate_language_alternatives_are_rejected_case_insensitively():
    assert_error(packet('<dc:title><rdf:Alt><rdf:li xml:lang="en-US">a</rdf:li>'
                        '<rdf:li xml:lang="EN-us">b</rdf:li></rdf:Alt></dc:title>'),
                 "duplicate_property")


@pytest.mark.parametrize("body,attributes", [
    ('<crs:A>text<rdf:Seq/></crs:A>', ''),
    ('<crs:A><rdf:Seq><crs:A>1</crs:A></rdf:Seq></crs:A>', ''),
    ('<crs:A><rdf:Seq/><rdf:Seq/></crs:A>', ''),
    ('<crs:A><crs:B>1</crs:B></crs:A>', ''),
    ('<crs:A rdf:parseType="Literal"><crs:B/></crs:A>', ''),
    ('<crs:A rdf:parseType="Collection"/>', ''),
    ('<crs:A rdf:resource="https://example.invalid/">1</crs:A>', ''),
    ('<crs:A rdf:datatype="urn:type"><rdf:Seq/></crs:A>', ''),
    ('<crs:A rdf:nodeID="external"/>', ''),
    ('<crs:A><rdf:Description rdf:parseType="Resource"/></crs:A>', ''),
    ('<crs:A crs:B="1">2</crs:A>', ''),
    ('<crs:A xml:base="https://example.invalid/"/>', ''),
    ('', 'Exposure2012="1"'),
    ('', 'rdf:nodeID="node"'),
    ('', 'xml:base="https://example.invalid/"'),
])
def test_ambiguous_malformed_or_unsupported_rdf_is_not_best_effort_imported(body, attributes):
    assert_error(packet(body, attributes), "invalid_rdf")


@pytest.mark.parametrize("raw", [
    b'<notXmp/>',
    f'<rdf:RDF xmlns:rdf="{RDF}"/>'.encode(),
    f'<rdf:RDF xmlns:rdf="{RDF}"><rdf:Bag/></rdf:RDF>'.encode(),
    f'<rdf:RDF xmlns:rdf="{RDF}">text<rdf:Description/></rdf:RDF>'.encode(),
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><one/><two/></x:xmpmeta>',
])
def test_malformed_rdf_envelopes_are_rejected(raw):
    assert_error(raw, "invalid_rdf")


@pytest.mark.parametrize("raw", [
    b'<unbound:RDF/>', b'<a><b></a>', b'<a/>trailing', b'<a/><a/>',
    packet(attributes='crs:A="1" crs:A="2"'),
    packet('<crs:A>&unknown;</crs:A>'),
])
def test_xml_well_formedness_is_owned_by_expat(raw):
    assert_error(raw, "xml")


@pytest.mark.parametrize("codec,declaration", [
    ("utf-8", "UTF-8"), ("utf-8-sig", "UTF-8"),
    ("utf-16", "UTF-16"), ("utf-16-le", "UTF-16LE"), ("utf-16-be", "UTF-16BE"),
])
def test_utf8_and_utf16_preserve_original_bytes_bom_and_digest(codec, declaration):
    text = f'<?xml version="1.0" encoding="{declaration}"?>' + packet(
        '<crs:Name>人像 Café</crs:Name>').decode()
    raw = text.encode(codec)
    doc = X.parse(raw)
    assert doc["raw"] == raw
    assert doc["sha256"] == hashlib.sha256(raw).hexdigest()
    assert doc["properties"] == {"Name": "人像 Café"}


@pytest.mark.parametrize("encoding", ["ISO-8859-1", "US-ASCII", "UTF-7", "windows-1252"])
def test_other_declared_encodings_are_explicitly_rejected_even_for_ascii_bytes(encoding):
    raw = f'<?xml version="1.0" encoding="{encoding}"?>'.encode() + packet()
    assert_error(raw, "encoding")


@pytest.mark.parametrize("raw", [
    b'<?xml version="1.0" encoding="UTF-16"?><a/>',
    ('<?xml version="1.0" encoding="UTF-8"?><a/>').encode("utf-16"),
    b'\xffinvalid', b'<a>\x00</a>', '<a/>'.encode('utf-32'),
])
def test_mismatched_malformed_or_unsupported_byte_encodings_are_rejected(raw):
    assert_error(raw, "encoding")


def test_xml11_is_not_silently_accepted_as_xml10():
    assert_error(b'<?xml version="1.1"?>' + packet(), "xml_version")


@pytest.mark.parametrize("declaration", [
    '<!DOCTYPE x SYSTEM "file:///etc/passwd">',
    '<!DOCTYPE x SYSTEM "https://attacker.invalid/external.dtd">',
    '<!DOCTYPE x [<!ENTITY a "expanded">]>',
    '<!DOCTYPE x [<!ENTITY % a SYSTEM "file:///etc/passwd">%a;]>',
    '<!ENTITY x "standalone declaration">',
    '<!-- <!ENTITY x "even a declaration marker in a comment is forbidden"> -->',
])
@pytest.mark.parametrize("codec", ["utf-8", "utf-16", "utf-16-be"])
def test_dtd_entity_and_parameter_entity_declarations_are_denied_after_decoding(declaration, codec):
    assert_error((declaration + packet().decode()).encode(codec), "forbidden_xml")


def test_inert_standard_packet_is_retained_without_becoming_a_write_permission():
    raw = ('<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'.encode()
           + packet(attributes='crs:A="1"') + b'\n   <?xpacket end="r"?>')
    doc = X.parse(raw)
    assert doc["raw"] == raw
    assert doc["metadata"]["packet"] == {"present": True, "writable": False}


@pytest.mark.parametrize("raw", [
    b'<?xml-stylesheet href="https://attacker.invalid/a.xsl"?>' + packet(),
    b'<?python import os?>' + packet(),
    b'<?xpacket begin="" id="wrong"?>' + packet(),
    b'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>' + packet(),
    packet() + b'<?xpacket end="w"?>',
    packet('<?xpacket end="w"?>'),
])
def test_nonstandard_misplaced_unpaired_or_executable_pis_are_rejected(raw):
    assert_error(raw, "processing_instruction")


@pytest.mark.parametrize("raw", [b"", b" " * (1024 * 1024 + 1)])
def test_raw_size_bound_is_checked_before_xml_parsing(raw):
    assert_error(raw, "size")


@pytest.mark.parametrize("raw", ["<x/>", bytearray(b"<x/>"), memoryview(b"<x/>")])
def test_only_immutable_raw_bytes_are_accepted(raw):
    assert_error(raw, "type")


def test_exact_1mib_snapshot_is_accepted_without_counting_packet_padding_as_content():
    # External XML whitespace is raw input, but not RDF text or parser node data.
    base = packet(attributes='crs:A="1"')
    raw = base + b" " * (X.MAX_BYTES - len(base))
    assert len(X.parse(raw)["raw"]) == X.MAX_BYTES


def test_depth_limit_is_enforced_during_xml_callbacks():
    raw = ("<a>" * (X.MAX_DEPTH + 1) + "</a>" * (X.MAX_DEPTH + 1)).encode()
    assert_error(raw, "limit")


def test_node_limit_counts_elements_comments_and_processing_instructions():
    raw = ("<a>" + "<b/>" * X.MAX_NODES + "</a>").encode()
    assert_error(raw, "limit")
    assert_error(("<a>" + "<!---->" * X.MAX_NODES + "</a>").encode(), "limit")


def test_structured_report_wrapper_depth_is_bounded_independently_of_xml_depth():
    body = ('<crs:Nested rdf:parseType="Resource">' * 17 +
            '<crs:Value>1</crs:Value>' + '</crs:Nested>' * 17)
    # XML depth is below 32, but explicit report fields wrappers exceed 32.
    assert_error(packet(body), "limit")


def test_individual_text_attribute_and_aggregate_text_limits():
    assert_error(packet('<crs:A>' + 'a' * (X.MAX_VALUE_CHARS + 1) + '</crs:A>'), "limit")
    assert_error(packet(attributes='crs:A="' + 'a' * (X.MAX_VALUE_CHARS + 1) + '"'), "limit")
    body = ''.join(f'<crs:P{i}>' + 'a' * X.MAX_VALUE_CHARS + f'</crs:P{i}>' for i in range(5))
    assert_error(packet(body), "limit")


def test_property_limit_applies_across_descriptions_and_nested_structures():
    body = ''.join(f'<crs:P{i}>1</crs:P{i}>' for i in range(X.MAX_PROPERTIES + 1))
    assert_error(packet(body), "limit")
    nested = '<crs:Outer rdf:parseType="Resource">' + body + '</crs:Outer>'
    assert_error(packet(nested), "limit")


def test_array_attribute_namespace_and_name_limits():
    body = '<crs:A><rdf:Seq>' + '<rdf:li>1</rdf:li>' * (X.MAX_ARRAY_ITEMS + 1) + '</rdf:Seq></crs:A>'
    assert_error(packet(body), "limit")
    attrs = ' '.join(f'crs:P{i}="1"' for i in range(X.MAX_ATTRIBUTES + 1))
    assert_error(packet(attributes=attrs), "limit")
    namespaces = ' '.join(f'xmlns:n{i}="urn:n:{i}"' for i in range(X.MAX_NAMESPACES + 1))
    assert_error(f'<a {namespaces}/>'.encode(), "limit")
    name = 'a' * (X.MAX_NAME_CHARS + 1)
    assert_error(f'<{name}/>'.encode(), "limit")


def test_unpatched_expat_fails_closed_without_parsing(monkeypatch):
    monkeypatch.setattr(X.expat, "version_info", (2, 7, 1))
    def must_not_parse(*args, **kwargs):
        raise AssertionError("Unpatched parser was constructed")
    monkeypatch.setattr(X.expat, "ParserCreate", must_not_parse)
    assert_error(packet(), "parser_version")


@pytest.mark.parametrize("basename", ["../a.xmp", "/tmp/a.xmp", "a\\b.xmp", "a\x00b", "x" * 256])
def test_basename_cannot_be_a_path_or_unbounded_display_label(basename):
    with pytest.raises(X.XmpDocumentError) as caught:
        X.parse(packet(), basename=basename)
    assert caught.value.code == "basename"


def test_read_preserves_exact_bytes_digest_and_file_contents(tmp_path):
    source = tmp_path / "original.xmp"
    raw = b'\xef\xbb\xbf' + packet(attributes='crs:A="1"') + b'\n   '
    source.write_bytes(raw)
    before = source.stat()
    doc = X.read(source)
    after = source.stat()
    assert doc["raw"] == raw == source.read_bytes()
    assert doc["sha256"] == hashlib.sha256(raw).hexdigest()
    assert doc["basename"] == source.name
    assert (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
        after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)


def test_symlink_leaf_and_symlink_parent_are_not_followed(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    source = real / "source.xmp"
    source.write_bytes(packet())
    leaf_link = tmp_path / "linked.xmp"
    leaf_link.symlink_to(source)
    directory_link = tmp_path / "linked_directory"
    directory_link.symlink_to(real, target_is_directory=True)
    for path in (leaf_link, directory_link / source.name):
        with pytest.raises(X.XmpDocumentError) as caught:
            X.read(path)
        assert caught.value.code == "io"


def test_directories_and_fifos_are_not_read_as_documents(tmp_path):
    with pytest.raises(X.XmpDocumentError) as caught:
        X.read(tmp_path)
    assert caught.value.code == "file_type"
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "fifo.xmp"
        os.mkfifo(fifo)
        with pytest.raises(X.XmpDocumentError) as caught:
            X.read(fifo)
        assert caught.value.code == "file_type"


def test_overlarge_file_is_rejected_before_read(tmp_path, monkeypatch):
    source = tmp_path / "too-large.xmp"
    with source.open("wb") as handle:
        handle.truncate(X.MAX_BYTES + 1)
    def must_not_read(*args, **kwargs):
        raise AssertionError("Overlarge source was read")
    monkeypatch.setattr(os, "read", must_not_read)
    with pytest.raises(X.XmpDocumentError) as caught:
        X.read(source)
    assert caught.value.code == "size"


def test_concurrent_source_mutation_is_rejected_before_parsing(tmp_path, monkeypatch):
    source = tmp_path / "changing.xmp"
    source.write_bytes(packet(attributes='crs:A="1"'))
    original_read = os.read
    changed = False
    def mutate_after_read(fd, count):
        nonlocal changed
        chunk = original_read(fd, count)
        if not changed:
            changed = True
            source.write_bytes(packet(attributes='crs:A="12345"'))
        return chunk
    monkeypatch.setattr(os, "read", mutate_after_read)
    with pytest.raises(X.XmpDocumentError) as caught:
        X.read(source)
    assert caught.value.code == "changed"


def test_leaf_replacement_is_rejected_even_if_open_descriptor_was_unchanged(tmp_path, monkeypatch):
    source = tmp_path / "replaced.xmp"
    source.write_bytes(packet())
    replacement = tmp_path / "new.xmp"
    replacement.write_bytes(packet())
    original_read = os.read
    replaced = False
    def replace_after_read(fd, count):
        nonlocal replaced
        chunk = original_read(fd, count)
        if not replaced:
            replaced = True
            replacement.replace(source)
        return chunk
    monkeypatch.setattr(os, "read", replace_after_read)
    with pytest.raises(X.XmpDocumentError) as caught:
        X.read(source)
    assert caught.value.code == "changed"


def test_missing_file_and_unsafe_paths_produce_reportable_errors(tmp_path):
    with pytest.raises(X.XmpDocumentError) as caught:
        X.read(tmp_path / "missing.xmp")
    assert caught.value.code == "io"
    for path in ("", b"bytes.xmp", "nul\x00.xmp", "a" * 4097):
        with pytest.raises(X.XmpDocumentError) as caught:
            X.read(path)
        assert caught.value.code == "unsafe_path"


def test_relative_path_read_uses_the_same_no_follow_contract(tmp_path, monkeypatch):
    source = tmp_path / "relative.xmp"
    source.write_bytes(packet(attributes='crs:A="1"'))
    monkeypatch.chdir(tmp_path)
    assert X.read(Path("relative.xmp"))["properties"] == {"A": "1"}
