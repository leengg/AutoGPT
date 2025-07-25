import json
import types
from typing import Any, Type, TypeVar, Union, cast, get_args, get_origin, overload

from prisma import Json as PrismaJson


class ConversionError(ValueError):
    pass


def __convert_list(value: Any) -> list:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    elif isinstance(value, dict):
        return list(value.items())
    elif isinstance(value, str):
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return [value]
        else:
            return [value]
    else:
        return [value]


def __convert_dict(value: Any) -> dict:
    if isinstance(value, str):
        try:
            result = json.loads(value)
            if isinstance(result, dict):
                return result
            else:
                return {"value": result}
        except json.JSONDecodeError:
            return {"value": value}  # Fallback conversion
    elif isinstance(value, list):
        return {i: value[i] for i in range(len(value))}
    elif isinstance(value, tuple):
        return {i: value[i] for i in range(len(value))}
    elif isinstance(value, dict):
        return value
    else:
        return {"value": value}


def __convert_tuple(value: Any) -> tuple:
    if isinstance(value, (str, list, set)):
        return tuple(value)
    elif isinstance(value, dict):
        return tuple(value.items())
    elif isinstance(value, (int, float, bool)):
        return (value,)
    elif isinstance(value, tuple):
        return value
    else:
        return (value,)


def __convert_set(value: Any) -> set:
    if isinstance(value, (str, list, tuple)):
        return set(value)
    elif isinstance(value, dict):
        return set(value.items())
    elif isinstance(value, set):
        return value
    else:
        return {value}


def __convert_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    else:
        return json.dumps(value)


NUM = TypeVar("NUM", int, float)


def __convert_num(value: Any, num_type: Type[NUM]) -> NUM:
    if isinstance(value, (list, dict, tuple, set)):
        return num_type(len(value))
    elif isinstance(value, num_type):
        return value
    else:
        try:
            return num_type(float(value))
        except (ValueError, TypeError):
            return num_type(0)  # Fallback conversion


def __convert_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        if value.lower() in ["true", "1"]:
            return True
        else:
            return False
    else:
        return bool(value)


def _try_convert(value: Any, target_type: Any, raise_on_mismatch: bool) -> Any:
    origin = get_origin(target_type)
    args = get_args(target_type)

    # Handle Union types (including Optional which is Union[T, None])
    if origin is Union or origin is types.UnionType:
        # Handle None values for Optional types
        if value is None:
            if type(None) in args:
                return None
            elif raise_on_mismatch:
                raise TypeError(f"Value {value} is not of expected type {target_type}")
            else:
                return value

        # Try to convert to each type in the union, excluding None
        non_none_types = [arg for arg in args if arg is not type(None)]

        # Try each type in the union, using the original raise_on_mismatch behavior
        for arg_type in non_none_types:
            try:
                return _try_convert(value, arg_type, raise_on_mismatch)
            except (TypeError, ValueError, ConversionError):
                continue

        # If no conversion succeeded
        if raise_on_mismatch:
            raise TypeError(f"Value {value} is not of expected type {target_type}")
        else:
            return value

    if origin is None:
        origin = target_type
    if origin not in [list, dict, tuple, str, set, int, float, bool]:
        return value

    # Handle the case when value is already of the target type
    if isinstance(value, origin):
        if not args:
            return value
        else:
            # Need to convert elements
            if origin is list:
                return [convert(v, args[0]) for v in value]
            elif origin is tuple:
                # Tuples can have multiple types
                if len(args) == 1:
                    return tuple(convert(v, args[0]) for v in value)
                else:
                    return tuple(convert(v, t) for v, t in zip(value, args))
            elif origin is dict:
                key_type, val_type = args
                return {
                    convert(k, key_type): convert(v, val_type) for k, v in value.items()
                }
            elif origin is set:
                return {convert(v, args[0]) for v in value}
            else:
                return value
    elif raise_on_mismatch:
        raise TypeError(f"Value {value} is not of expected type {target_type}")
    else:
        # Need to convert value to the origin type
        if origin is list:
            value = __convert_list(value)
            if args:
                return [convert(v, args[0]) for v in value]
            else:
                return value
        elif origin is dict:
            value = __convert_dict(value)
            if args:
                key_type, val_type = args
                return {
                    convert(k, key_type): convert(v, val_type) for k, v in value.items()
                }
            else:
                return value
        elif origin is tuple:
            value = __convert_tuple(value)
            if args:
                if len(args) == 1:
                    return tuple(convert(v, args[0]) for v in value)
                else:
                    return tuple(convert(v, t) for v, t in zip(value, args))
            else:
                return value
        elif origin is str:
            return __convert_str(value)
        elif origin is set:
            value = __convert_set(value)
            if args:
                return {convert(v, args[0]) for v in value}
            else:
                return value
        elif origin is int:
            return __convert_num(value, int)
        elif origin is float:
            return __convert_num(value, float)
        elif origin is bool:
            return __convert_bool(value)
        else:
            return value


T = TypeVar("T")
TT = TypeVar("TT")


def type_match(value: Any, target_type: Type[T]) -> T:
    return cast(T, _try_convert(value, target_type, raise_on_mismatch=True))


@overload
def convert(value: Any, target_type: Type[T]) -> T: ...


@overload
def convert(value: Any, target_type: Any) -> Any: ...


def convert(value: Any, target_type: Any) -> Any:
    try:
        if isinstance(value, PrismaJson):
            value = value.data
        return _try_convert(value, target_type, raise_on_mismatch=False)
    except Exception as e:
        raise ConversionError(f"Failed to convert {value} to {target_type}") from e


class FormattedStringType(str):
    string_format: str

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        _ = source_type  # unused parameter required by pydantic
        return handler(str)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        json_schema = handler(core_schema)
        json_schema["format"] = cls.string_format
        return json_schema


class MediaFileType(FormattedStringType):
    """
    MediaFile is a string that represents a file. It can be one of the following:
        - Data URI: base64 encoded media file. See https://developer.mozilla.org/en-US/docs/Web/URI/Schemes/data/
        - URL: Media file hosted on the internet, it starts with http:// or https://.
        - Local path (anything else): A temporary file path living within graph execution time.

    Note: Replace this type alias into a proper class, when more information is needed.
    """

    string_format = "file"


class LongTextType(FormattedStringType):
    string_format = "long-text"


class ShortTextType(FormattedStringType):
    string_format = "short-text"
