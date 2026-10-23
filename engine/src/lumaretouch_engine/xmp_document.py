"""Bounded, read-only XMP/RDF ingestion. SOURCE IMPLEMENTATION, runtime UNRUN.

This is the untrusted-document boundary, not CameraRaw compatibility or a pixel
operation. Python's maintained Expat binding owns XML tokenization, namespaces,
well-formedness and character references. We do not introduce a home-grown XML
parser merely to make this small I/O boundary Rust. Numeric/rendering work stays
separate. Expat must be security-patched; see Python's XML security documentation.

Only UTF-8/UTF-16, one RDF graph describing one subject, and the bounded XMP RDF
forms below are accepted. Unsupported RDF syntax is an explicit error, never a
best-effort import. DTDs, declared entities, external entities and arbitrary PIs
are forbidden. Standard XML escapes remain legal. URI values are inert strings:
there is no resolver, XInclude processing, network access, eval, or source write.

``read(path)`` and ``parse(raw, basename='')`` return the original bytes, their
SHA-256, a basename, exact-namespace CameraRaw properties and report metadata.
Plain RDF Seq items become ordered lists. Bag/Alt arrays, qualified literals,
structures and URI resources remain report dictionaries; no mapping is attempted.
XML's standard text/attribute normalization affects parsed values only. The raw
bytes are retained exactly, including BOM, namespace prefixes and packet padding.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass, field
from xml.parsers import expat


CAMERA_RAW_NS = "http://ns.adobe.com/camera-raw-settings/1.0/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XMP_META_NS = "adobe:ns:meta/"
MAX_BYTES = 1024 * 1024
MAX_DEPTH = 32
MAX_REPORT_DEPTH = 32
MAX_NODES = 4096
MAX_PROPERTIES = 512
MAX_ARRAY_ITEMS = 2048
MAX_TEXT_CHARS = 262144
MAX_VALUE_CHARS = 65536
MAX_NAME_CHARS = 1024
MAX_ATTRIBUTES = 128
MAX_NAMESPACES = 128
MIN_EXPAT_VERSION = (2, 7, 2)

_SEP = "\x1f"  # Invalid in an XML namespace URI/name; cannot create collisions.
_RDF = "{" + RDF_NS + "}"
_XML = "{" + XML_NS + "}"
_FORBIDDEN_DECLARATION = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_XML_ENCODING = re.compile(r"\bencoding\s*=\s*(['\"])([^'\"]+)\1")
_PACKET_BEGIN = re.compile(
    r"\s*begin\s*=\s*(['\"])(?:\ufeff)?\1\s+"
    r"id\s*=\s*(['\"])W5M0MpCehiHzreSzNTczkc9d\2\s*")
_PACKET_END = re.compile(r"\s*end\s*=\s*(['\"])([wr])\1\s*")


class XmpDocumentError(ValueError):
    """Reportable, fail-closed error; ``code`` is suitable for UI branching."""

    def __init__(self, message: str, *, code: str = "invalid_xmp"):
        super().__init__(message)
        self.code = code


def _fail(message: str, code: str = "invalid_rdf") -> None:
    raise XmpDocumentError(message, code=code)


def _expanded(name: str) -> str:
    if len(name) > MAX_NAME_CHARS:
        _fail("XMP expanded name exceeds the name limit", "limit")
    if _SEP not in name:
        return name
    namespace, local = name.split(_SEP, 1)
    return "{" + namespace + "}" + local


def _namespace(name: str) -> str:
    return name[1:].rsplit("}", 1)[0] if name.startswith("{") else ""


def _decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith((b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00",
                       b"\x00\x00\x00<", b"<\x00\x00\x00")):
        _fail("XMP supports UTF-8 and UTF-16, not UTF-32", "encoding")
    if raw.startswith(b"\xff\xfe"):
        codec, encoding = "utf-16", "utf-16-le"
    elif raw.startswith(b"\xfe\xff"):
        codec, encoding = "utf-16", "utf-16-be"
    elif raw.startswith(b"<\x00"):
        codec = encoding = "utf-16-le"
    elif raw.startswith(b"\x00<"):
        codec = encoding = "utf-16-be"
    else:
        codec, encoding = "utf-8-sig", "utf-8"
    try:
        text = raw.decode(codec, errors="strict")
    except UnicodeError as error:
        raise XmpDocumentError("XMP is not supported UTF-8/UTF-16 text",
                               code="encoding") from error
    # This is a conservative declaration deny-list after decoding, not XML
    # tokenization. Expat independently rejects declarations through handlers.
    # A literal declaration marker in a comment/CDATA is also intentionally denied.
    if _FORBIDDEN_DECLARATION.search(text):
        _fail("DTD and entity declarations are forbidden in XMP", "forbidden_xml")
    if "\x00" in text:
        _fail("NUL or an unsupported byte encoding in XMP", "encoding")
    # Expat validates the complete XML declaration. Here we reject unsupported
    # declared codecs before parsing; no arbitrary Python codec is ever selected.
    if text.startswith("<?xml"):
        declaration = text[:text.find("?>") + 2] if "?>" in text else text
        match = _XML_ENCODING.search(declaration)
        if match:
            _check_encoding(match.group(2), encoding)
    return text, encoding


def _check_encoding(declared: str, actual: str) -> None:
    declared = declared.lower()
    allowed = {"utf-8", "utf-16", "utf-16le", "utf-16be"}
    if declared not in allowed:
        _fail("Only UTF-8/UTF-16 XML declarations are supported", "encoding")
    matches = {"utf-8": {"utf-8"},
               "utf-16-le": {"utf-16", "utf-16le"},
               "utf-16-be": {"utf-16", "utf-16be"}}
    if declared not in matches[actual]:
        _fail("XMP declaration does not match the original byte encoding", "encoding")


@dataclass(slots=True)
class _Node:
    name: str
    attrs: dict[str, str]
    children: list[_Node] = field(default_factory=list)
    chunks: list[str] = field(default_factory=list)
    text_chars: int = 0

    @property
    def text(self) -> str:
        return "".join(self.chunks)


class _Tree:
    def __init__(self, encoding: str):
        self.encoding = encoding
        self.root: _Node | None = None
        self.stack: list[_Node] = []
        self.node_count = 0
        self.text_chars = 0
        self.namespace_count = 0
        self.namespaces: set[str] = set()
        self.packet_begin = False
        self.packet_end: str | None = None
        self.xml_version = "1.0"

    def count_node(self) -> None:
        self.node_count += 1
        if self.node_count > MAX_NODES:
            _fail("XMP exceeds the XML node limit", "limit")

    def charge(self, value: str) -> None:
        if len(value) > MAX_VALUE_CHARS:
            _fail("XMP text or attribute exceeds the value limit", "limit")
        self.text_chars += len(value)
        if self.text_chars > MAX_TEXT_CHARS:
            _fail("XMP exceeds the aggregate text limit", "limit")

    def start(self, name: str, attrs: dict[str, str]) -> None:
        self.count_node()
        if len(self.stack) >= MAX_DEPTH:
            _fail("XMP exceeds the XML depth limit", "limit")
        if len(attrs) > MAX_ATTRIBUTES:
            _fail("XMP exceeds the per-node attribute limit", "limit")
        for value in attrs.values():
            self.charge(value)
        node = _Node(_expanded(name), {_expanded(k): v for k, v in attrs.items()})
        if self.stack:
            self.stack[-1].children.append(node)
        elif self.root is None:
            self.root = node
        else:
            _fail("XMP must contain exactly one XML root")
        self.stack.append(node)

    def end(self, name: str) -> None:
        self.stack.pop()  # Expat checks matching tags and document well-formedness.

    def data(self, value: str) -> None:
        if not self.stack:
            # Packet padding is bounded by MAX_BYTES, not a property value.
            if value.strip():
                _fail("Unexpected text outside the XMP XML root", "xml")
            return
        self.charge(value)
        if self.stack:
            node = self.stack[-1]
            node.text_chars += len(value)
            if node.text_chars > MAX_VALUE_CHARS:
                _fail("XMP property exceeds the text limit", "limit")
            node.chunks.append(value)

    def namespace(self, prefix: str | None, uri: str | None) -> None:
        self.namespace_count += 1
        if self.namespace_count > MAX_NAMESPACES:
            _fail("XMP exceeds the namespace-declaration limit", "limit")
        if len(prefix or "") > MAX_NAME_CHARS or len(uri or "") > MAX_NAME_CHARS:
            _fail("XMP namespace exceeds the name limit", "limit")
        self.charge(uri or "")
        if uri:
            self.namespaces.add(uri)

    def comment(self, value: str) -> None:
        self.count_node()
        self.charge(value)

    def declaration(self, version: str, encoding: str | None, standalone: int) -> None:
        if version != "1.0":
            _fail("Only XML 1.0 XMP documents are supported", "xml_version")
        self.xml_version = version
        if encoding:
            _check_encoding(encoding, self.encoding)

    def pi(self, target: str, value: str) -> None:
        self.count_node()
        self.charge(value)
        if target != "xpacket" or self.stack or len(value) > 256:
            _fail("Only inert standard XMP packet instructions are allowed",
                  "processing_instruction")
        if self.root is None and not self.packet_begin and _PACKET_BEGIN.fullmatch(value):
            self.packet_begin = True
            return
        end = _PACKET_END.fullmatch(value)
        if self.root is not None and self.packet_begin and self.packet_end is None and end:
            self.packet_end = end.group(2)
            return
        _fail("Invalid, misplaced or duplicate XMP packet instruction",
              "processing_instruction")


def _deny_xml(*args: object) -> None:
    _fail("DTD, entity declarations and external entities are forbidden",
          "forbidden_xml")


def _parse_tree(raw: bytes, encoding: str) -> _Tree:
    if expat.version_info < MIN_EXPAT_VERSION:
        _fail("XMP requires security-patched Expat 2.7.2 or newer; update the runtime",
              "parser_version")
    tree = _Tree(encoding)
    parser = expat.ParserCreate(namespace_separator=_SEP)
    parser.buffer_text = True
    parser.StartElementHandler = tree.start
    parser.EndElementHandler = tree.end
    parser.CharacterDataHandler = tree.data
    parser.StartNamespaceDeclHandler = tree.namespace
    parser.CommentHandler = tree.comment
    parser.XmlDeclHandler = tree.declaration
    parser.ProcessingInstructionHandler = tree.pi
    parser.StartDoctypeDeclHandler = _deny_xml
    parser.EntityDeclHandler = _deny_xml
    parser.UnparsedEntityDeclHandler = _deny_xml
    parser.ExternalEntityRefHandler = _deny_xml
    parser.SkippedEntityHandler = _deny_xml
    parser.NotationDeclHandler = _deny_xml
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    # One bounded feed avoids repeated large-token reparsing. Never disable the
    # library's reparse deferral or create an external-entity parser/resolver.
    try:
        parser.Parse(raw, True)
    except expat.ExpatError as error:
        raise XmpDocumentError(
            f"Malformed XMP XML at line {error.lineno}, column {error.offset}",
            code="xml") from error
    if tree.root is None:
        _fail("XMP has no XML root", "xml")
    if tree.packet_begin != (tree.packet_end is not None):
        _fail("XMP packet must have a matching begin and end", "processing_instruction")
    return tree


class _Rdf:
    def __init__(self):
        self.property_count = 0

    def put(self, target: dict, name: str, value: object) -> None:
        if name in target:
            _fail(f"Duplicate/conflicting XMP property: {name}", "duplicate_property")
        self.property_count += 1
        if self.property_count > MAX_PROPERTIES:
            _fail("XMP exceeds the property limit", "limit")
        target[name] = value

    @staticmethod
    def property_name(name: str, *, qualified: bool = False) -> None:
        namespace = _namespace(name)
        if not namespace or namespace == XML_NS or (
                namespace == RDF_NS and not (qualified and name == _RDF + "value")):
            _fail("XMP property names must use a non-reserved namespace")

    @staticmethod
    def no_text(node: _Node) -> None:
        if node.text.strip():
            _fail("Mixed text and RDF structure are not supported")

    @staticmethod
    def language(node: _Node, inherited: str | None) -> str | None:
        # xml:lang="" clears, rather than inventing an empty language qualifier.
        return node.attrs.get(_XML + "lang", inherited) or None

    @staticmethod
    def literal(value: str, language: str | None, datatype: str | None = None) -> object:
        if language and datatype:
            _fail("An RDF literal cannot have both language and datatype")
        if language is None and datatype is None:
            return value
        out = {"kind": "literal", "value": value}
        if language is not None:
            out["language"] = language
        if datatype is not None:
            out["datatype"] = datatype
        return out

    def fields(self, node: _Node, language: str | None, *, top: bool = False,
               resource_property: bool = False) -> dict:
        self.no_text(node)
        language = self.language(node, language)
        fields: dict = {}
        for name, value in sorted(node.attrs.items()):
            if name == _XML + "lang":
                continue
            if name == _RDF + "about" and top:
                continue
            if name == _RDF + "parseType" and value == "Resource" and resource_property:
                continue
            self.property_name(name)
            self.put(fields, name, self.literal(value, language))
        for child in node.children:
            self.property_name(child.name, qualified=not top)
            self.put(fields, child.name, self.value(child, language))
        return dict(sorted(fields.items()))

    @staticmethod
    def structure(fields: dict) -> dict:
        if _RDF + "value" in fields:
            return {"kind": "qualified", "value": fields[_RDF + "value"],
                    "qualifiers": {k: v for k, v in fields.items() if k != _RDF + "value"}}
        return {"kind": "structure", "fields": fields}

    def value(self, node: _Node, inherited_language: str | None) -> object:
        language = self.language(node, inherited_language)
        attrs = {k: v for k, v in node.attrs.items() if k != _XML + "lang"}
        parse_type = attrs.get(_RDF + "parseType")
        if parse_type is not None:
            if parse_type != "Resource" or set(attrs) != {_RDF + "parseType"}:
                _fail("Unsupported or conflicting RDF parseType syntax")
            return self.structure(self.fields(node, language, resource_property=True))
        resource = attrs.get(_RDF + "resource")
        if resource is not None:
            if set(attrs) != {_RDF + "resource"} or node.children or node.text.strip():
                _fail("RDF resource cannot also contain a literal or structure")
            return {"kind": "resource", "uri": resource}
        datatype = attrs.get(_RDF + "datatype")
        if datatype is not None:
            if set(attrs) != {_RDF + "datatype"} or node.children:
                _fail("RDF datatype is only supported on a simple literal")
            return self.literal(node.text, language, datatype)
        for name in attrs:
            self.property_name(name)
        if attrs:
            if node.children or node.text.strip():
                _fail("RDF abbreviated structure cannot also contain text or children")
            return self.structure(self.fields(node, language))
        if not node.children:
            return self.literal(node.text, language)
        self.no_text(node)
        if len(node.children) != 1:
            _fail("RDF property requires one container or one resource description")
        child = node.children[0]
        if child.name == _RDF + "Description":
            return self.structure(self.fields(child, language))
        if child.name not in {_RDF + "Seq", _RDF + "Bag", _RDF + "Alt"}:
            _fail("Unsupported RDF property child; explicit resource structure required")
        self.no_text(child)
        if set(child.attrs) - {_XML + "lang"}:
            _fail("Unexpected RDF array attributes")
        language = self.language(child, language)
        if len(child.children) > MAX_ARRAY_ITEMS:
            _fail("XMP exceeds the RDF array-item limit", "limit")
        items = []
        languages = set()
        for item in child.children:
            if item.name != _RDF + "li":
                _fail("RDF arrays may contain only rdf:li items")
            value = self.value(item, language)
            if child.name == _RDF + "Alt" and isinstance(value, dict) and "language" in value:
                key = value["language"].lower()
                if key in languages:
                    _fail("Duplicate RDF Alt language", "duplicate_property")
                languages.add(key)
            items.append(value)
        kind = child.name[len(_RDF):]
        if kind == "Seq" and all(isinstance(item, str) for item in items):
            return items
        return {"kind": "array", "container": kind, "items": items}


def _check_report(value: object) -> None:
    # Report wrappers add JSON levels beyond the XML element depth. Bound that
    # representation too, so downstream preview/portable-metadata readers do not
    # receive a deeper value than this document boundary promises.
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_REPORT_DEPTH:
            _fail("XMP structured report exceeds the value-depth limit", "limit")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _document(tree: _Tree) -> tuple[dict, dict]:
    rdf = tree.root
    assert rdf is not None
    envelope: dict = {}
    if rdf.name in {"{" + XMP_META_NS + "}xmpmeta", "{" + XMP_META_NS + "}xapmeta"}:
        _Rdf.no_text(rdf)
        # Toolkit labels are inert metadata; inherited xml:lang is handled below.
        allowed = {"{" + XMP_META_NS + "}xmptk", _XML + "lang"}
        if set(rdf.attrs) - allowed or len(rdf.children) != 1:
            _fail("XMP envelope must contain exactly one RDF graph and safe metadata")
        envelope = dict(sorted(rdf.attrs.items()))
        rdf = rdf.children[0]
    if rdf.name != _RDF + "RDF":
        _fail("XMP must have rdf:RDF or x:xmpmeta as its root")
    _Rdf.no_text(rdf)
    if set(rdf.attrs) - {_XML + "lang"} or not rdf.children:
        _fail("RDF graph must contain descriptions, without graph-reference attributes")
    language = _Rdf.language(rdf, envelope.get(_XML + "lang") or None)
    reader = _Rdf()
    values: dict = {}
    subjects = set()
    forms: dict = {}
    for description in rdf.children:
        if description.name != _RDF + "Description":
            _fail("XMP RDF graph may contain only rdf:Description nodes")
        subjects.add(description.attrs.get(_RDF + "about", ""))
        if len(subjects) > 1:
            _fail("Multiple RDF subjects cannot be merged into one XMP preset")
        fields = reader.fields(description, language, top=True)
        for name, value in fields.items():
            if name in values:
                _fail(f"Duplicate/conflicting XMP property: {name}", "duplicate_property")
            values[name] = value
        for name in description.attrs:
            if name in fields:
                forms[name] = {"source": "attribute"}
        for child in description.children:
            form = {"source": "element"}
            if child.children and child.children[0].name in {
                    _RDF + "Seq", _RDF + "Bag", _RDF + "Alt"}:
                form["container"] = child.children[0].name[len(_RDF):]
            forms[child.name] = form
    crs_prefix = "{" + CAMERA_RAW_NS + "}"
    for value in values.values():
        _check_report(value)
    properties = {k[len(crs_prefix):]: v for k, v in sorted(values.items())
                  if k.startswith(crs_prefix)}
    metadata = {
        "encoding": tree.encoding,
        "xml_version": tree.xml_version,
        "parser": expat.EXPAT_VERSION,
        "description_count": len(rdf.children),
        "subjects": sorted(subjects),
        "namespaces": sorted(tree.namespaces),
        "node_count": tree.node_count,
        "property_count": reader.property_count,
        "text_characters": tree.text_chars,
        "packet": {"present": tree.packet_begin,
                   "writable": tree.packet_end == "w" if tree.packet_begin else None},
        "envelope_attributes": envelope,
        "property_forms": dict(sorted(forms.items())),
        "other_properties": {k: v for k, v in sorted(values.items())
                             if not k.startswith(crs_prefix)},
    }
    return properties, metadata


def parse(raw: bytes, *, basename: str = "") -> dict:
    """Parse an immutable bounded snapshot; retain exact original bytes/hash.

    ``basename`` is a display label, never a path to resolve. Results include no
    absolute source path, filesystem handle, external resolver or executable data.
    """
    if not isinstance(raw, bytes):
        _fail("XMP input must be immutable bytes", "type")
    if not isinstance(basename, str) or len(basename) > 255 or any(
            char in basename for char in ("/", "\\", "\x00")):
        _fail("XMP basename must be a bounded filename, not a path", "basename")
    if not raw or len(raw) > MAX_BYTES:
        _fail("XMP must be nonempty and at most 1 MiB", "size")
    _text, encoding = _decode(raw)
    tree = _parse_tree(raw, encoding)
    properties, metadata = _document(tree)
    metadata["byte_length"] = len(raw)
    return {"raw": raw, "sha256": hashlib.sha256(raw).hexdigest(),
            "basename": basename, "properties": properties, "metadata": metadata}


def _fingerprint(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _open_parent(path: str) -> tuple[int, str]:
    # Walk every component through pinned directory descriptors. O_NOFOLLOW on
    # just the leaf would still follow an attacker-controlled parent symlink.
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY") or (
            os.open not in os.supports_dir_fd):
        _fail("Safe no-follow XMP reads are unavailable on this platform", "unsafe_path")
    parts = path.split(os.sep)
    if not parts[-1] or parts[-1] in {".", ".."}:
        _fail("XMP source must name a regular file", "file_type")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    parent = os.open(os.sep if os.path.isabs(path) else ".", flags)
    try:
        for part in parts[:-1]:
            if part in {"", "."}:
                continue
            next_parent = os.open(part, flags, dir_fd=parent)
            os.close(parent)
            parent = next_parent
        return parent, parts[-1]
    except BaseException:
        os.close(parent)
        raise


def read(path: str | os.PathLike[str]) -> dict:
    """Read a stable ordinary file without following symlinks or modifying it.

    A bounded read plus before/after fstat rejects observable concurrent changes;
    the final directory-entry check also rejects replacement/unlink of the leaf.
    This is a snapshot consistency check, not a filesystem lock or a guarantee
    against a privileged writer changing data after the snapshot was acquired.
    """
    try:
        source = os.fspath(path)
    except TypeError as error:
        raise XmpDocumentError("XMP source must be a filesystem path", code="type") from error
    if not isinstance(source, str) or not source or "\x00" in source or len(source) > 4096:
        _fail("XMP source must be a bounded text path", "unsafe_path")
    parent = fd = None
    try:
        parent, basename = _open_parent(source)
        flags = (os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                 getattr(os, "O_CLOEXEC", 0))
        fd = os.open(basename, flags, dir_fd=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            _fail("XMP source must be a regular file", "file_type")
        if not 0 < before.st_size <= MAX_BYTES:
            _fail("XMP must be nonempty and at most 1 MiB", "size")
        chunks: list[bytes] = []
        size = 0
        while size <= MAX_BYTES:
            chunk = os.read(fd, min(65536, MAX_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            chunks.append(chunk)
        after = os.fstat(fd)
        current = os.stat(basename, dir_fd=parent, follow_symlinks=False)
        if size > MAX_BYTES:
            _fail("XMP grew beyond the 1 MiB read limit", "size")
        if _fingerprint(before) != _fingerprint(after) or (
                _fingerprint(after) != _fingerprint(current)) or size != before.st_size:
            _fail("XMP source changed while it was being read; select it again", "changed")
        raw = b"".join(chunks)
    except OSError as error:
        raise XmpDocumentError("Cannot safely open/read the XMP source file",
                               code="io") from error
    finally:
        if fd is not None:
            os.close(fd)
        if parent is not None:
            os.close(parent)
    return parse(raw, basename=basename)
