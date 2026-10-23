"""Registered server.py admission and final-write adapter; runtime validation UNRUN."""
from .export_target_size_policy import parse_target_size
from .export_target_size_writer import write_target_size


def request_policy(command, *, format, bit_depth):
    """Call before queue admission; store returned wire dict in frozen opts."""
    policy = parse_target_size(command.get("target_size"), format=format, bit_depth=bit_depth)
    if policy is not None and command.get("quality") is not None:
        raise ValueError("请选择品质或近似目标大小，不可同时提交两种模式")
    return None if policy is None else policy.wire()


def write_delivery(frame, path, *, target_size=None, watermark=None, cancelled=lambda: False,
                   progress=None, **options):
    """Replace only the final write_delivery8 call, after all edited-pixel stages.

    Marked and clean copies get their own size budget and honest receipts. Existing
    watermark partial-delivery policy is retained; successful copies stay on disk.
    """
    if target_size is None:
        from .watermark_delivery import write_delivery8
        return write_delivery8(frame, path, watermark=watermark, **options)
    options = dict(options)
    options.pop("quality", None)
    options.pop("tiff_compression", None)
    def write(pixels, destination):
        return write_target_size(pixels, destination, target_size=target_size,
                                 cancelled=cancelled, progress=progress, **options)
    if not watermark:
        return write(frame, path)
    from .watermark_delivery import _deliver, DeliveryError
    try:
        return _deliver(frame, path, watermark, write)
    except DeliveryError as error:
        error.target_size = getattr(error.__cause__, "target_size", None)
        raise
