import copy
import logging
from symbolic import Archive, SymCache, parse_addr
from symbolic.demangle import demangle_name

alternative_arch = {
    "x86": ["x86", "x86_64"]
}


class ResolvedStacktrace:
    def __init__(self, score=0, frames=[]):
        self.score = score
        self.frames = frames


def find_arch_object(archive, arch):
    if arch in alternative_arch:
        arch_list = alternative_arch[arch]
    else:
        arch_list = [arch]

    for arch in arch_list:
        try:
            object = archive.get_object(arch=arch)
            return object
        except Exception:
            pass


def digest_symbol(symbol):
    try:
        item = symbol[0]
        if item.lang == "unknown":
            return None
        return item
    except Exception:
        pass


def getLogger():
    return logging.getLogger("glitchtip.difs")  # FIXME


class StacktraceProcessor:
    """
    This class process an event with exceptions. Try to load DIF and resolve
    the stacktrace
    """

    def __init__(self):
        pass

    @classmethod
    def resolve_stacktrace(cls, event, symbol_file):
        # Process event
        try:
            contexts = event.get("contexts")
            if contexts is None:
                # Nodejs crash report doesn't contain this field.
                # In future, we need to support.
                return
            arch = contexts.get("device").get("arch")

            # Process the first exception only.
            exceptions = event.get("exception").get("values")
            stacktrace = exceptions[0].get("stacktrace")
        except Exception:
            getLogger().error(f"StacktraceProcessor: Invalid event: {event}")
            return

        # Open symbol file
        try:
            archive = Archive.open(symbol_file)
            archive.open(symbol_file)
            obj = find_arch_object(archive, arch)
            sym_cache = SymCache.from_object(obj)
        except Exception as e:
            getLogger().error(f"StacktraceProcessor: Open symbol file failed: {e}")
            return

        try:
            frames = stacktrace.get("frames")
            score = 0
            resolved_frames = []
            for frame in frames:
                frame = copy.copy(frame)

                image_addr = parse_addr(frame.get("image_addr"))
                instruction_addr = parse_addr(frame.get("instruction_addr"))
                function = frame.get("function")
                addr = instruction_addr - image_addr
                symbol = sym_cache.lookup(addr)
                digested_symbol = digest_symbol(symbol)
                if (
                    digested_symbol is not None and
                    digested_symbol.symbol == function
                ):
                    frame["resolved"] = True
                    frame["filename"] = digested_symbol.filename
                    frame["lineNo"] = digested_symbol.line
                    frame["function"] = demangle_name(digested_symbol.symbol)
                    score = score + 1

                resolved_frames.append(frame)

            return ResolvedStacktrace(
                score=score,
                frames=resolved_frames
            )
        except Exception as e:
            getLogger().error(f"StacktraceProcessor: Unexpected error: {e}")

    @classmethod
    def update_frames(cls, event, frames):
        try:
            data = event.data
            exceptions = data.get("exception").get("values")
            stacktrace = exceptions[0].get("stacktrace")
            stacktrace["frames"] = frames
            event.data = data
        except Exception as e:
            getLogger().error(f"StacktraceProcessor: Unexpected error: {e}")
            pass
