"""Thin HTTP client for the local 360 Hextile backend.

Stdlib only (urllib). Default base URL: http://127.0.0.1:8000.
No app logic — pure proxy helpers for the MCP server and Codex install.
"""

from __future__ import annotations

import http.client
import hashlib
import json
import math
import os
import re
import socket
import uuid
from fractions import Fraction
from contextlib import contextmanager
from contextvars import ContextVar
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Optional

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_S = 30.0
LONG_OPERATION_TIMEOUT_S = 300.0  # Export, sequence extraction, and local vision

APP_DOWN_MSG = (
    "360 Hextile isn't running. Launch 360 Hextile, then retry."
)
UPGRADE_MSG = (
    "Upgrade 360 Hextile (needs workflows/run). "
    "This plugin requires a build with POST /api/workflows/run."
)
BATCH_UNAVAILABLE_MSG = (
    "Batch workflows are unavailable. Enable Batch in 360 Hextile "
    "(HEXTILE_BATCH_WORKFLOWS_ENABLED), then retry."
)
_BATCH_KNOWN_404 = (
    "unknown_preflight",
    "unknown_job",
    "unknown_workflow",
    "preview_unavailable",
)

_ERROR_BODY_SNIPPET = 800
_REQUEST_HEADERS: ContextVar[Mapping[str, str]] = ContextVar(
    "hextile_request_headers", default={}
)

_WORKSPACE_HANDLE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_WORKSPACE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_WORKSPACE_SUFFIX = re.compile(r"[1-9][0-9]{0,15}\Z")
MAX_WORKSPACE_GENERATION = 2**53 - 1

_OUTPUT_PROFILES = {"png-master/1", "shader-linear-rgba-exr/1", "dome-png/1",
                    "shader-raster-still/1"}
_OUTPUT_OWNER = {"request_id", "shader", "project_context_witness", "base",
                 "studio_surface_id", "expected_edit_sequence"}


def _absolute_task_path(value: Any) -> bool:
    """Native task syntax is independent of the MCP host filesystem."""
    return type(value) is str and (PureWindowsPath(value).is_absolute()
                                  or PurePosixPath(value).is_absolute())


def _safe_output_leaf(name: Any, suffixes: set[str]) -> bool:
    """The native writer's portable leaf rule, with a profile-specific suffix."""
    if (type(name) is not str or not 1 <= len(name) <= 255
            or name[-1] in {".", " "}
            or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name)
            or PureWindowsPath(name).is_reserved()
            or re.match(r"^(?:COM|LPT)[1-9¹²³](?:\.|$)", name, re.I)):
        return False
    return PureWindowsPath(name).suffix.lower() in suffixes


def _safe_task_output_path(value: Any, suffixes: set[str]) -> bool:
    if not _absolute_task_path(value) or len(value) > 4096:
        return False
    native = PureWindowsPath(value) if PureWindowsPath(value).is_absolute() else PurePosixPath(value)
    return _safe_output_leaf(native.name, suffixes)


def _native_pose(output: Mapping[str, Any]) -> bool:
    return all(type(output[key]) in (int, float) and math.isfinite(output[key])
               and lo <= output[key] <= hi for key, lo, hi in
               (("fov_deg", 10, 360), ("pan", -180, 180), ("tilt", -90, 90), ("roll", -180, 180))
               if key in output)


def _valid_raster_still_output(output: Mapping[str, Any]) -> bool:
    if (not {"projection", "encoding", "output_path"} <= set(output)
            or output["encoding"] not in {"png", "jpg"}):
        return False
    if not _safe_task_output_path(output["output_path"],
                                  {".png"} if output["encoding"] == "png" else {".jpg", ".jpeg"}):
        return False
    if output["projection"] == "equirectangular":
        return (set(output) == {"projection", "encoding", "output_path", "width", "height"}
                and type(output["width"]) is int and output["width"] in {1024, 2048, 4096}
                and type(output["height"]) is int and output["height"] * 2 == output["width"])
    return (output["projection"] in {"fulldome", "fulldome_angular"}
            and set(output) <= {"projection", "encoding", "output_path", "diameter",
                                "fov_deg", "pan", "tilt", "roll"}
            and type(output.get("diameter")) is int
            and output["diameter"] in {1024, 2048, 4096, 8192}
            and _native_pose(output))


def _valid_linear_exr_output(output: Mapping[str, Any]) -> bool:
    if (not {"width", "height"} <= set(output)
            or set(output) - {"width", "height", "projection", "fov_deg", "pan", "tilt", "roll", "output_path"}
            or type(output["width"]) is not int or type(output["height"]) is not int):
        return False
    projection = output.get("projection", "equirectangular")
    if projection == "equirectangular":
        return (2 <= output["width"] <= 4096
                and output["width"] == output["height"] * 2
                and not {"fov_deg", "pan", "tilt", "roll"} & set(output))
    return (projection in {"fulldome", "fulldome_angular"}
            and output["width"] == output["height"]
            and output["width"] in {1024, 2048, 4096, 8192}
            and _safe_task_output_path(output.get("output_path"), {".exr"})
            and _native_pose(output))


def _valid_dome_job_output(output: Any, *, raster: bool) -> bool:
    if type(output) is not dict or output.get("projection") not in {
            "equirectangular", "fulldome", "fulldome_angular"}:
        return False
    if raster:
        if output.get("encoding") not in {"png", "jpg"}:
            return False
        if output["projection"] == "equirectangular":
            if (not {"width", "height"} <= set(output)
                    or set(output) - {"projection", "encoding", "width", "height", "file"}
                    or type(output["width"]) is not int or output["width"] not in {1024, 2048, 4096}
                    or type(output["height"]) is not int or output["height"] * 2 != output["width"]):
                return False
        elif (type(output.get("diameter")) is not int
                or output["diameter"] not in {1024, 2048, 4096, 8192}
                or set(output) - {"projection", "encoding", "diameter", "fov_deg", "pan", "tilt", "roll", "file"}):
            return False
    else:
        if (output["projection"] == "equirectangular" or type(output.get("diameter")) is not int
                or output["diameter"] not in {1024, 2048, 4096, 8192}
                or "fov_deg" not in output
                or set(output) - {"projection", "diameter", "fov_deg", "pan", "tilt", "roll", "file"}):
            return False
    if not _native_pose(output):
        return False
    if "file" not in output:
        return True
    file = output["file"]
    if raster:
        suffixes = {".png"} if output["encoding"] == "png" else {".jpg", ".jpeg"}
        return _safe_output_leaf(file, suffixes)
    return (type(file) is str and re.fullmatch(r"domes/[A-Za-z0-9_-]{1,64}\.png", file) is not None)


def _shader_output_receipt(operation: str, args: Mapping[str, Any], result: Any,
                           *, mutation: bool = False) -> dict:
    """Close the native output boundary, retaining its actual task destination."""
    def invalid() -> HextileClientError:
        return HextileClientError("Invalid bounded Shader output receipt",
            kind="shader_output_outcome_unknown" if mutation else "other",
            receipt={"request_id": args["request_id"]} if mutation else None)

    try:
        if type(result) is not dict or len(json.dumps(result, ensure_ascii=False,
                                                      allow_nan=False).encode("utf-8")) > 32768:
            raise invalid()
        if result.get("request_id") != args["request_id"]:
            raise invalid()
        keys = set(result)
        for field in ("output_path", "destination_project"):
            if field in result and not _absolute_task_path(result[field]):
                raise invalid()

        if operation in {"preview", "preflight"}:
            full = {"schema", "request_id", "operation", "state", "shader",
                    "project_context_witness"}
            if ((keys != {"request_id", "state"} and
                 (not full <= keys or keys - full - {"transition", "reason"}))
                    or result["state"] not in {"pending", "applied", "refused", "unknown", "expired"}):
                raise invalid()
            if "schema" in result and (result["schema"] != 1
                    or result["operation"] != "shader_capture_output"
                    or result["shader"] != args["shader"]
                    or result["project_context_witness"] != args["project_context_witness"]):
                raise invalid()
            if "reason" in result and (type(result["reason"]) is not str
                    or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", result["reason"]) is None):
                raise invalid()
            if "transition" in result:
                transition = result["transition"]
                base = {key: args["base"][key] for key in
                        ("working_revision", "document_hash", "source_hash")}
                if (type(transition) is not dict or not {"from_edit_sequence", "to_edit_sequence",
                        "from_base", "to_base"} <= set(transition)
                        or set(transition) - {"from_edit_sequence", "to_edit_sequence", "from_base",
                            "to_base", "from_doc_generation", "to_doc_generation"}
                        or any(type(transition[key]) is not int or transition[key] != args["expected_edit_sequence"]
                               for key in ("from_edit_sequence", "to_edit_sequence"))
                        or any(type(transition[key]) is not dict
                               or any(transition[key].get(field) != value for field, value in base.items())
                               or set(transition[key]) - set(base) - {"manifest_hash"}
                               for key in ("from_base", "to_base"))
                        or any(type(transition[key]) is not str or len(transition[key]) > 128
                               for key in ("from_doc_generation", "to_doc_generation") if key in transition)):
                    raise invalid()
        elif operation == "get_preview":
            if result.get("state") in {"pending", "unavailable"}:
                if keys != {"request_id", "state"}:
                    raise invalid()
            elif (result.get("state") != "ready" or keys != {"request_id", "state", "width",
                    "height", "sha256", "format"} or type(result["width"]) is not int
                    or type(result["height"]) is not int or not 0 < result["width"] <= 1024
                    or not 0 < result["height"] <= 512 or result["width"] * result["height"] > 524288
                    or type(result["sha256"]) is not str
                    or _WORKSPACE_DIGEST.fullmatch(result["sha256"]) is None
                    or result["format"] != "rgb8-srgb-top-origin"):
                raise invalid()
        elif operation == "release_preview":
            if keys != {"request_id", "released"} or result["released"] is not True:
                raise invalid()
        elif operation in {"still", "get_job", "stop_job"}:
            allowed = {"request_id", "profile", "job", "publication", "state", "output_name", "output_path", "reason"}
            if (not {"request_id", "profile", "job"} <= keys or keys - allowed
                    or operation == "still" and "state" not in result
                    or result["profile"] != args["profile"]
                    or result["profile"] not in _OUTPUT_PROFILES
                    or "state" in result and result["state"] not in {"recovered", "queued", "processing",
                         "completed", "publication_failed", "failed", "cancelled", "stop_requested",
                         "stopped", "Interrupted"}
                    or "publication" in result and result["publication"] not in {
                         "unknown", "complete", "failed", "queued", "processing", "completed",
                         "cancelled", "stop_requested", "stopped", "Interrupted"}
                    or "output_name" in result and type(result["output_name"]) is not str):
                raise invalid()
            job = result["job"]
            if type(job) is not dict:
                raise invalid()
            state = job.get("state")
            if state not in {"queued", "processing", "completed", "failed", "cancelled",
                             "stop_requested", "stopped", "Interrupted"}:
                raise invalid()
            profile = result["profile"]
            if profile == "png-master/1":
                if (set(job) != {"id", "shader_ref", "state", "progress", "output_identity"}
                        or job["shader_ref"] != args["shader"]
                        or job["output_identity"] is not None and (type(job["output_identity"]) is not dict
                            or set(job["output_identity"]) != {"render_id", "node_id"}
                            or type(job["output_identity"]["render_id"]) is not str
                            or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job["output_identity"]["render_id"]) is None
                            or job["output_identity"]["node_id"] is not None
                            and (type(job["output_identity"]["node_id"]) is not str
                                 or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job["output_identity"]["node_id"]) is None))):
                    raise invalid()
                job_id = job["id"]
            elif profile == "shader-linear-rgba-exr/1":
                if (set(job) != {"job_id", "state", "progress", "profile", "output"}
                        or job["profile"] != profile or job["output"] is not None
                        and not _safe_output_leaf(job["output"], {".exr"})):
                    raise invalid()
                job_id = job["job_id"]
            else:
                if (set(job) != {"job_id", "state", "progress", "idempotency_key", "output"}
                        or job["idempotency_key"] != args["request_id"]):
                    raise invalid()
                output = job["output"]
                if output is not None and not _valid_dome_job_output(output, raster=profile == "shader-raster-still/1"):
                    raise invalid()
                job_id = job["job_id"]
            if (type(job_id) is not str or re.fullmatch(r"[0-9a-f]{32}", job_id) is None
                    or type(job["progress"]) not in (int, float)
                    or not math.isfinite(job["progress"]) or not 0 <= job["progress"] <= 1):
                raise invalid()
            suffixes = ({".exr"} if profile == "shader-linear-rgba-exr/1" else
                        {".png"} if profile in {"png-master/1", "dome-png/1"} else
                        {".png"} if type(job.get("output")) is dict and job["output"].get("encoding") == "png"
                        else {".jpg", ".jpeg"} if type(job.get("output")) is dict and job["output"].get("encoding") == "jpg"
                        else {".png", ".jpg", ".jpeg"})
            if ("output_name" in result and not _safe_output_leaf(result["output_name"], suffixes)
                    or "output_path" in result and not _safe_task_output_path(result["output_path"], suffixes)):
                raise invalid()
        elif operation == "bundle":
            if (keys != {"request_id", "state", "output_name", "output_path", "resource_count", "resource_bytes"}
                    or result["state"] != "saved" or type(result["output_name"]) is not str
                    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,239}\.hexshader", result["output_name"]) is None
                    or type(result["resource_count"]) is not int or result["resource_count"] < 0
                    or type(result["resource_bytes"]) is not int or result["resource_bytes"] < 0):
                raise invalid()
        elif operation == "project":
            if (keys != {"request_id", "state", "shader_id", "target_name", "destination_project"}
                    or result["state"] not in {"accepted", "deleted", "uncertain"}
                    or type(result["shader_id"]) is not str
                    or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", result["shader_id"]) is None
                    or type(result["target_name"]) is not str or not 1 <= len(result["target_name"]) <= 256
                    or any(ch in result["target_name"] for ch in "/\\:\r\n\x00")):
                raise invalid()
        else:
            raise invalid()
        return result
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise invalid() from exc


def _valid_shader_creation_status(result: Any, args: Mapping[str, Any], *, complete: bool) -> bool:
    if type(result) is not dict:
        return False
    common = {"schema", "request_id", "operation", "scope", "state", "project_context_witness"}
    try:
        if (not common <= set(result) or set(result) - common - {"receipt", "error"}
                or result["schema"] != 1 or result["request_id"] != args["request_id"]
                or result["operation"] not in {"shader_create_asset", "shader_import_bundle"} or result["scope"] != "creation"
                or result["project_context_witness"] != args["project_context_witness"]
                or type(result["state"]) is not str
                or result["state"] not in {"pending", "unknown", "refused", "expired", "saved"}
                or complete and result["state"] != "saved"
                or len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 32768):
            return False
        if "error" in result and (result["state"] != "refused" or type(result["error"]) is not dict
                or set(result["error"]) - {"message", "code"}):
            return False
        if result["state"] != "saved":
            return "receipt" not in result
        receipt = result.get("receipt")
        return (type(receipt) is dict and set(receipt) == ({"shader", "working_revision",
                "document_hash", "source_hash", "manifest_hash"} | ({"bundle_sha256"} if result["operation"] == "shader_import_bundle" else set()))
                and (result["operation"] != "shader_import_bundle" or type(receipt["bundle_sha256"]) is str
                     and _WORKSPACE_DIGEST.fullmatch(receipt["bundle_sha256"]) is not None)
                and type(receipt["shader"]) is dict
                and set(receipt["shader"]) == {"origin", "shaderId"}
                and receipt["shader"]["origin"] in {"user", "project"}
                and type(receipt["shader"]["shaderId"]) is str
                and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", receipt["shader"]["shaderId"]) is not None
                and type(receipt["working_revision"]) is int and receipt["working_revision"] == 1
                and all(type(receipt[key]) is str and _WORKSPACE_DIGEST.fullmatch(receipt[key])
                        for key in ("document_hash", "source_hash"))
                and (receipt["manifest_hash"] is None or
                     type(receipt["manifest_hash"]) is str and
                     _WORKSPACE_DIGEST.fullmatch(receipt["manifest_hash"]) is not None))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _shader_output_args(operation: str, args: Mapping[str, Any]) -> None:
    common = {"shader", "project_context_witness", "request_id"}
    fields = {
        "preview": (_OUTPUT_OWNER | {"output"}, set()),
        "preflight": (_OUTPUT_OWNER | {"profile", "output"}, {"allow_unpreviewed_revision"}),
        "still": (_OUTPUT_OWNER | {"preflight_request_id", "profile"}, set()),
        "get_preview": (common, {"image"}),
        "release_preview": (common, set()),
        "get_job": (common | {"profile"}, set()),
        "stop_job": (common | {"profile"}, set()),
        "bundle": (_OUTPUT_OWNER | {"expected_looks", "expected_provenance_hash"}, {"output_path"}),
        "project": (_OUTPUT_OWNER, {"destination_project"}),
    }
    required, optional = fields[operation]
    if not isinstance(args, Mapping) or required - args.keys() or set(args) - required - optional:
        raise HextileClientError("Expected closed Shader output arguments", status_code=422, kind="other")
    _native_shader_args("state", {key: args[key] for key in ("shader", "project_context_witness")})
    for key in ("request_id", "preflight_request_id"):
        if key in args:
            try:
                valid = type(args[key]) is str and str(uuid.UUID(args[key])) == args[key] and uuid.UUID(args[key]).version == 4
            except (TypeError, ValueError, AttributeError):
                valid = False
            if not valid:
                raise HextileClientError("Expected canonical output UUID", status_code=422, kind="other")
    if operation in {"preview", "preflight", "still", "bundle", "project"}:
        base = args["base"]
        if (not isinstance(base, Mapping) or set(base) != {"kind", "working_revision", "document_hash", "source_hash"}
                or base["kind"] != "saved" or type(base["working_revision"]) is not int or base["working_revision"] < 1
                or any(type(base[key]) is not str or not _WORKSPACE_DIGEST.fullmatch(base[key]) for key in
                       ("document_hash", "source_hash"))
                or any(type(args[key]) is not str or not args[key] for key in ("studio_surface_id",))
                or type(args["expected_edit_sequence"]) is not int or args["expected_edit_sequence"] < 0):
            raise HextileClientError("Invalid saved output owner", status_code=422, kind="other")
    if operation in {"preflight", "still", "get_job", "stop_job"} and (
            type(args["profile"]) is not str or args["profile"] not in _OUTPUT_PROFILES):
        raise HextileClientError("Unsupported Shader still profile", status_code=422, kind="other")
    if operation in {"preview", "preflight"}:
        output = args["output"]
        if not isinstance(output, Mapping):
            raise HextileClientError("Invalid Shader output settings", status_code=422, kind="other")
        if operation == "preview":
            projection = output.get("projection")
            fields = ({"projection", "pan", "tilt", "roll", "supersampling"}
                      if projection == "equirectangular" else
                      {"projection", "diameter", "fov_deg", "pan", "tilt", "roll", "supersampling"})
            required = fields - {"supersampling"}
            valid = (type(projection) is str and projection in {"equirectangular", "fulldome", "fulldome_angular"}
                     and required <= output.keys() and set(output) <= fields)
        else:
            if args["profile"] == "shader-raster-still/1":
                valid = _valid_raster_still_output(output)
            elif args["profile"] == "shader-linear-rgba-exr/1":
                valid = _valid_linear_exr_output(output)
            else:
                shape = {"png-master/1": ({"width", "height"}, {"supersampling", "output_path"}),
                         "dome-png/1": ({"projection", "diameter", "fov_deg", "pan", "tilt", "roll"},
                                        {"output_path"})}[args["profile"]]
                valid = shape[0] <= output.keys() and set(output) <= shape[0] | shape[1]
        if not valid:
            raise HextileClientError("Unsupported closed Shader output settings", status_code=422, kind="other")
    for field in ("output_path", "destination_project"):
        value = args.get("output", {}).get(field) if operation == "preflight" else args.get(field)
        if value is not None and not _absolute_task_path(value):
            raise HextileClientError("Expected absolute task destination", status_code=422, kind="other")
        if operation == "preflight" and field == "output_path" and value is not None:
            profile = args["profile"]
            suffixes = ({".exr"} if profile == "shader-linear-rgba-exr/1" else
                        {".png"} if profile in {"png-master/1", "dome-png/1"} else
                        {".png"} if args["output"]["encoding"] == "png" else {".jpg", ".jpeg"})
            if not _safe_task_output_path(value, suffixes):
                raise HextileClientError("Invalid native output filename", status_code=422, kind="other")
    if operation == "get_preview" and "image" in args and type(args["image"]) is not bool:
        raise HextileClientError("Image opt-in must be boolean", status_code=422, kind="other")
    if "allow_unpreviewed_revision" in args and type(args["allow_unpreviewed_revision"]) is not bool:
        raise HextileClientError("Native unpreviewed revision confirmation must be boolean", status_code=422, kind="other")


def _native_shader_args(operation: str, args: Mapping[str, Any]) -> None:
    common = {"shader", "project_context_witness"}
    expected = (common if operation == "state" else
                common | {"request_id"} if operation == "status" else
                common | {"request_id", "base", "expected_working_digest"} |
                ({"title"} if operation == "rename" else set()))
    optional = {"expected_owner_generation", "library_intent", "confirmation_scope"} if operation in {"rename", "delete"} else set()
    if not isinstance(args, Mapping) or expected - args.keys() or set(args) - expected - optional:
        raise HextileClientError("Expected closed native Shader operation arguments", status_code=422, kind="other")
    ref = args["shader"]
    if (not isinstance(ref, Mapping) or set(ref) != {"origin", "shaderId"}
            or ref["origin"] not in {"builtin", "user", "project"}
            or type(ref["shaderId"]) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", ref["shaderId"])
            or type(args["project_context_witness"]) is not str or not args["project_context_witness"]):
        raise HextileClientError("Invalid native Shader target", status_code=422, kind="other")
    if operation in {"status", "rename", "delete"}:
        try:
            valid = (type(args["request_id"]) is str and str(uuid.UUID(args["request_id"])) == args["request_id"]
                     and uuid.UUID(args["request_id"]).version == 4)
        except (ValueError, AttributeError):
            valid = False
        if not valid:
            raise HextileClientError("Invalid native Shader request_id", status_code=422, kind="other")
    if operation in {"rename", "delete"}:
        base = args["base"]
        if (not isinstance(base, Mapping) or set(base) != {"kind", "working_revision", "document_hash", "source_hash"}
                or base["kind"] != "saved" or type(base["working_revision"]) is not int
                or base["working_revision"] < 1 or any(type(base[key]) is not str or not _WORKSPACE_DIGEST.fullmatch(base[key])
                                                        for key in ("document_hash", "source_hash"))
                or type(args["expected_working_digest"]) is not str
                or not _WORKSPACE_DIGEST.fullmatch(args["expected_working_digest"])
                or (operation == "rename" and (type(args["title"]) is not str or not args["title"] or len(args["title"]) > 256))
                or args.get("library_intent") not in {None, "saved"}
                or ("confirmation_scope" in args and args["confirmation_scope"] !=
                    {"operation": operation, "shader": dict(ref)})
                or (args.get("library_intent") == "saved" and "confirmation_scope" not in args)
                or ("expected_owner_generation" in args and
                    (type(args["expected_owner_generation"]) is not str or not args["expected_owner_generation"]))):
            raise HextileClientError("Invalid native Shader rename", status_code=422, kind="other")


def _native_read_args(args: Mapping[str, Any], required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(args, Mapping) or required - args.keys() or set(args) - required - optional:
        raise HextileClientError("Expected closed Shader read arguments", status_code=422, kind="other")
    witness = args.get("project_context_witness")
    if type(witness) is not str or not 1 <= len(witness) <= 256:
        raise HextileClientError("Invalid Project witness", status_code=422, kind="other")
    if "shader" in required:
        _native_shader_args("state", {"shader": args["shader"], "project_context_witness": witness})
    if "limit" in args and (type(args["limit"]) is not int or not 1 <= args["limit"] <=
                            (50 if "shelf" in optional else 20)):
        raise HextileClientError("Invalid page limit", status_code=422, kind="other")
    if "cursor" in args and (type(args["cursor"]) is not str or len(args["cursor"]) > 8192):
        raise HextileClientError("Invalid page cursor", status_code=422, kind="other")
    if "search" in args and (type(args["search"]) is not str or len(args["search"]) > 128):
        raise HextileClientError("Invalid discovery search", status_code=422, kind="other")
    if "shelf" in args and args["shelf"] not in {"builtin", "user", "project"}:
        raise HextileClientError("Invalid discovery shelf", status_code=422, kind="other")
    if "kind" in args and args["kind"] not in {"revisions", "checkpoints"}:
        raise HextileClientError("Invalid history kind", status_code=422, kind="other")


def _native_history_args(operation: str, args: Mapping[str, Any]) -> None:
    common = {"shader", "project_context_witness", "base", "expected_working_digest"}
    owner = {"library_intent", "confirmation_scope", "studio_surface_id", "expected_edit_sequence"}
    fields = {
        "shader_save_look": ({"title"}, {"include_overrides", "look_id", "expected_look_envelope_hash"}),
        "shader_apply_look": ({"look_id", "expected_look_envelope_hash"}, set()),
        "shader_rename_look": ({"look_id", "expected_look_envelope_hash", "title"}, set()),
        "shader_delete_look": ({"look_id", "expected_look_envelope_hash"}, set()),
        "shader_checkpoint_save": ({"title"}, {"target"}),
        "shader_checkpoint_rename": ({"checkpoint_id", "expected_name", "title"}, set()),
        "shader_checkpoint_remove": ({"checkpoint_id", "expected_name"}, set()),
        "shader_restore_revision": (set(), {"target", "checkpoint_id"}),
        "shader_copy_revision": ({"destination_origin"}, {"target", "checkpoint_id", "title"}),
        "shader_history_preview": ({"mode"}, {"preview_operation"}),
        "shader_history_compact": ({"mode", "preview_token"}, set()),
        "shader_history_uncompact": ({"mode", "preview_token"}, set()),
    }
    if operation not in fields or not isinstance(args, Mapping):
        raise HextileClientError("Unknown Shader history operation", status_code=422, kind="other")
    required, optional = fields[operation]
    required = common | required | (set() if operation == "shader_history_preview" else {"request_id"})
    if required - args.keys() or set(args) - required - optional - owner:
        raise HextileClientError("Invalid Shader history fields", status_code=422, kind="other")
    _native_shader_args("state", {key: args[key] for key in ("shader", "project_context_witness")})
    base = args["base"]
    if (not isinstance(base, Mapping) or set(base) != {"kind", "working_revision", "document_hash", "source_hash"}
            or base["kind"] != "saved" or type(base["working_revision"]) is not int or base["working_revision"] < 1
            or any(type(base[key]) is not str or not _WORKSPACE_DIGEST.fullmatch(base[key])
                   for key in ("document_hash", "source_hash"))
            or type(args["expected_working_digest"]) is not str
            or not _WORKSPACE_DIGEST.fullmatch(args["expected_working_digest"])):
        raise HextileClientError("Invalid Shader history base", status_code=422, kind="other")
    if operation != "shader_history_preview":
        try:
            valid_id = str(uuid.UUID(args["request_id"])) == args["request_id"] and uuid.UUID(args["request_id"]).version == 4
        except (ValueError, TypeError, AttributeError):
            valid_id = False
        if not valid_id:
            raise HextileClientError("Invalid Shader history request_id", status_code=422, kind="other")
    saved = args.get("library_intent") == "saved"
    if saved:
        if (args.get("confirmation_scope") != {"operation": operation if operation != "shader_history_preview"
                else "shader_history_retention", "shader": dict(args["shader"])}
                or any(key in args for key in ("studio_surface_id", "lease_id", "expected_edit_sequence"))):
            raise HextileClientError("Invalid saved history confirmation", status_code=422, kind="other")
    elif ("library_intent" in args or "confirmation_scope" in args
          or not {"studio_surface_id", "expected_edit_sequence"} <= args.keys()
          or any(type(args[key]) is not str or not args[key] for key in ("studio_surface_id",))
          or type(args["expected_edit_sequence"]) is not int or args["expected_edit_sequence"] < 0):
        raise HextileClientError("Invalid mounted history owner", status_code=422, kind="other")
    for key in ("title", "expected_name"):
        if key in args and (type(args[key]) is not str or not 1 <= len(args[key]) <= 256):
            raise HextileClientError("Invalid Shader history name", status_code=422, kind="other")
    for key in ("look_id", "checkpoint_id"):
        if key in args and (type(args[key]) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", args[key])):
            raise HextileClientError("Invalid Shader history ID", status_code=422, kind="other")
    for key in ("expected_look_envelope_hash", "preview_token"):
        if key in args and (type(args[key]) is not str or not _WORKSPACE_DIGEST.fullmatch(args[key])):
            raise HextileClientError("Invalid Shader history hash", status_code=422, kind="other")
    if "target" in args and (not isinstance(args["target"], Mapping)
            or set(args["target"]) != {"document_ref", "document_hash"}
            or type(args["target"]["document_ref"]) is not str
            or type(args["target"]["document_hash"]) is not str
            or not _WORKSPACE_DIGEST.fullmatch(args["target"]["document_hash"])):
        raise HextileClientError("Invalid Shader history target", status_code=422, kind="other")
    if operation in {"shader_restore_revision", "shader_copy_revision"} and (
            ("target" in args) == ("checkpoint_id" in args)):
        raise HextileClientError("History needs one exact target", status_code=422, kind="other")
    if operation == "shader_save_look" and (("look_id" in args) != ("expected_look_envelope_hash" in args)):
        raise HextileClientError("Look replacement needs an envelope hash", status_code=422, kind="other")
    if "include_overrides" in args and type(args["include_overrides"]) is not bool:
        raise HextileClientError("Invalid Look overrides choice", status_code=422, kind="other")
    if "mode" in args and args["mode"] not in {"current", "checkpoints"}:
        raise HextileClientError("Invalid history retention mode", status_code=422, kind="other")
    if "preview_operation" in args and args["preview_operation"] not in {"compact", "uncompact"}:
        raise HextileClientError("Invalid recoverable history preview", status_code=422, kind="other")
    if "destination_origin" in args and args["destination_origin"] not in {"user", "project"}:
        raise HextileClientError("Invalid copy destination", status_code=422, kind="other")


def _native_read_result(data: Any, *, kind: str, entries: int | None = None) -> dict:
    try:
        size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise HextileClientError("Malformed Shader read result", kind="other") from exc
    allowed = {
        "state": {"schema", "shader", "project_context_witness", "status", "provenance", "base",
                  "capability", "working_digest", "owner_generation", "title", "tags",
                  "document_schema", "draft_state", "writable", "save_state", "reasons",
                  "saved_values", "unaccepted_values", "mounted_values",
                  "bundle_state", "human_only"},
        "assets": {"schema", "project_context_witness", "entries", "next_cursor", "project"},
        "history": {"schema", "shader", "project_context_witness", "kind", "current",
                    "inventory_generation", "entries", "next_cursor"},
        "looks": {"schema", "shader", "project_context_witness", "provenance", "entries"},
        "conventions": {"schema", "project_context_witness", "digest", "writable",
                        "default_profile_id", "profiles", "reason"},
    }[kind]
    required = {
        "state": {"schema", "shader", "project_context_witness", "status", "provenance", "base",
                  "capability", "writable", "save_state"},
        "assets": {"schema", "project_context_witness", "entries", "next_cursor", "project"},
        "history": {"schema", "shader", "project_context_witness", "kind", "entries", "next_cursor"},
        "looks": {"schema", "shader", "project_context_witness", "provenance", "entries"},
        "conventions": {"schema", "project_context_witness", "digest", "writable", "profiles"},
    }[kind]
    entry_allowed = {
        "assets": {"shader", "title", "status", "reasons", "base"},
        "history": {"document_ref", "document_hash", "ordinal", "integrity", "publication",
                    "schema", "timestamp", "hash_suffix", "restore_eligible", "copy_eligible",
                    "eligibility_reason", "id", "name", "actor", "error", "target_family"},
        "looks": {"id", "title", "revision", "content_hash", "envelope_hash", "manifest_hash",
                  "frozen_document_revision", "frozen_document_hash"},
    }.get(kind)
    if (type(data) is not dict or size > 32768 or data.get("schema") != 1 or
            set(data) - allowed or required - set(data) or
            (kind == "state" and (data.get("status") not in {"saved", "unaccepted", "incomplete"}
                                  or data.get("provenance") not in {"saved", "mounted", "unaccepted", "incomplete"}
                                  or type(data.get("writable")) is not bool
                                  or ("human_only" in data and (type(data["human_only"]) is not dict
                                      or set(data["human_only"]) != {"permanent_history_purge",
                                          "developer_builtin_authoring", "physical_input"}
                                      or any(type(reason) is not str or len(reason) > 256
                                             for reason in data["human_only"].values())))

                                      or ("bundle_state" in data and (type(data["bundle_state"]) is not dict
                                          or set(data["bundle_state"]) != {"expected_looks", "expected_provenance_hash"}
                                          or type(data["bundle_state"]["expected_looks"]) is not list
                                          or len(data["bundle_state"]["expected_looks"]) > 32
                                          or any(type(row) is not dict or set(row) != {"id", "revision", "envelope_hash"}
                                                 or type(row["id"]) is not str or not 1 <= len(row["id"]) <= 128
                                                 or type(row["revision"]) is not int or row["revision"] < 1
                                                 or type(row["envelope_hash"]) is not str
                                                 or _WORKSPACE_DIGEST.fullmatch(row["envelope_hash"]) is None
                                                 for row in data["bundle_state"]["expected_looks"])
                                          or data["bundle_state"]["expected_provenance_hash"] is not None
                                          and (type(data["bundle_state"]["expected_provenance_hash"]) is not str
                                               or _WORKSPACE_DIGEST.fullmatch(data["bundle_state"]["expected_provenance_hash"]) is None))))) or
            (entries is not None and (type(data.get("entries")) is not list or
                                      len(data["entries"]) > entries or
                                      any(type(row) is not dict or set(row) - entry_allowed
                                          for row in data["entries"]))) or
            (kind == "conventions" and (type(data.get("profiles")) is not list or
                                         len(data["profiles"]) > 8)) or
            ("next_cursor" in data and data["next_cursor"] is not None and
             (type(data["next_cursor"]) is not str or len(data["next_cursor"]) > 8192))):
        raise HextileClientError("Malformed or unbounded Shader read result", kind="other")
    return data


_CREDIT_SOURCE_FIELDS = {"author", "title", "url", "contribution", "relationship", "contributors",
                         "evidence", "license", "license_status", "ai_assistance", "source_revision",
                         "source_digest"}


def _credit_source_fields(value: Any) -> bool:
    if type(value) is not dict or set(value) - _CREDIT_SOURCE_FIELDS:
        return False
    if any(type(item) is not str or len(item.encode("utf-8")) > 4096 for key, item in value.items()
           if key in {"author", "title", "url", "contribution", "license", "ai_assistance", "source_revision"}):
        return False
    if ("relationship" in value and value["relationship"] not in {"original", "adaptation", "inspiration"}) or (
            "license_status" in value and value["license_status"] not in
            {"unknown", "recorded", "user_declared", "conflicting"}):
        return False
    if "evidence" in value:
        row = value["evidence"]
        if (type(row) is not dict or not {"basis", "note"} <= set(row) or set(row) - {"basis", "note", "url"}
                or row["basis"] not in {"observed", "user_declared", "inferred"}
                or type(row["note"]) is not str or not 1 <= len(row["note"].encode("utf-8")) <= 512
                or ("url" in row and (type(row["url"]) is not str or len(row["url"]) > 4096))):
            return False
    if "source_digest" in value:
        row = value["source_digest"]
        if type(row) is not dict or set(row) != {"kind", "digest"} or any(type(item) is not str for item in row.values()):
            return False
    if "contributors" in value and (type(value["contributors"]) is not list
            or len(value["contributors"]) > 128 or not all(_credit_profile(item) for item in value["contributors"])):
        return False
    return True


def _credit_profile(value: Any) -> bool:
    if type(value) is not dict:
        return False
    if set(value) == {"id"}:
        return type(value["id"]) is str and _WORKSPACE_DIGEST.fullmatch(value["id"]) is not None
    if set(value) != {"snapshot"} or type(value["snapshot"]) is not dict:
        return False
    row = value["snapshot"]
    links = row.get("links", [])
    return (set(row) <= {"version", "name", "links"} and row.get("version") == 1
            and type(row.get("name")) is str and 1 <= len(row["name"]) <= 128
            and type(links) is list and len(links) <= 12
            and all(type(link) is dict and set(link) == {"label", "url"}
                    and all(type(item) is str for item in link.values()) for link in links))


def _credit_source_operations(value: Any, *, registration: bool) -> bool:
    if type(value) is not list or len(value) > 128 or (not registration and not value):
        return False
    for row in value:
        if type(row) is not dict:
            return False
        kind = row.get("kind")
        if kind == "append" and set(row) == {"kind", "row"}:
            if not _credit_source_fields(row["row"]):
                return False
        elif kind == "change" and set(row) == {"kind", "index", "set"}:
            if type(row["index"]) is not int or not 0 <= row["index"] < 128 or not _credit_source_fields(row["set"]):
                return False
        elif not registration and kind == "remove" and set(row) == {"kind", "index"}:
            if type(row["index"]) is not int or not 0 <= row["index"] < 128:
                return False
        elif not registration and kind == "reorder" and set(row) == {"kind", "order"}:
            if type(row["order"]) is not list or len(row["order"]) > 128 or any(
                    type(index) is not int or not 0 <= index < 128 for index in row["order"]):
                return False
        else:
            return False
    return True


def _credit_source_proposal(value: Any) -> bool:
    return (type(value) is dict and set(value) == {"schema", "expected_provenance_hash", "sources"}
            and type(value["schema"]) is int and value["schema"] == 1
            and (value["expected_provenance_hash"] is None or
                 (type(value["expected_provenance_hash"]) is str and
                  _WORKSPACE_DIGEST.fullmatch(value["expected_provenance_hash"]) is not None))
            and _credit_source_operations(value["sources"], registration=True))


def _credit_changes(value: Any) -> bool:
    if type(value) is not dict or not value or set(value) - {
            "author", "attribution", "license", "sources", "current", "record", "automatic_credit"}:
        return False
    if any(type(value[key]) is not str or len(value[key].encode("utf-8")) > 4096
           for key in ("author", "attribution", "license") if key in value):
        return False
    if "automatic_credit" in value and type(value["automatic_credit"]) is not bool:
        return False
    if "sources" in value and not _credit_source_operations(value["sources"], registration=False):
        return False
    if "current" in value:
        edits = value["current"]
        if type(edits) is not list or len(edits) > 128:
            return False
        for edit in edits:
            if type(edit) is not dict or edit.get("kind") not in {"add", "change", "remove"}:
                return False
            if edit["kind"] == "add":
                if (not {"kind", "contributor", "role"} <= set(edit)
                        or set(edit) - {"kind", "contributor", "role", "summary"}
                        or not _credit_profile(edit["contributor"])):
                    return False
            else:
                target = edit.get("target")
                if (type(target) is not dict or set(target) != {"index", "contributor", "role"}
                        or type(target["index"]) is not int or not 0 <= target["index"] < 128
                        or type(target["contributor"]) is not str):
                    return False
                if edit["kind"] == "remove" and set(edit) != {"kind", "target"}:
                    return False
                if edit["kind"] == "change":
                    patch = edit.get("set")
                    if (set(edit) != {"kind", "target", "set"} or type(patch) is not dict or not patch
                            or set(patch) - {"contributor", "role", "summary"}
                            or ("contributor" in patch and not _credit_profile(patch["contributor"]))
                            or ("role" in patch and patch["role"] not in {"shader-author", "shader-editor"})
                            or ("summary" in patch and patch["summary"] is not None and
                                (type(patch["summary"]) is not str or not 1 <= len(patch["summary"]) <= 1024))):
                        return False
            if edit.get("role", edit.get("target", {}).get("role")) not in {"shader-author", "shader-editor"}:
                return False
    if "record" in value:
        row = value["record"]
        if (type(row) is not dict or not {"kind", "contributor", "summary", "content"} <= set(row)
                or set(row) - {"kind", "contributor", "summary", "content", "previous", "corrects",
                               "replacement", "recorded_at"}
                or row["kind"] not in {"contribution", "correction"}
                or not _credit_profile(row["contributor"])
                or type(row["summary"]) is not str or not 1 <= len(row["summary"]) <= 1024
                or type(row["content"]) is not dict or set(row["content"]) != {"kind", "digest"}
                or row["content"]["kind"] != "hextile-shader-source-v1"
                or type(row["content"]["digest"]) is not str
                or _WORKSPACE_DIGEST.fullmatch(row["content"]["digest"]) is None):
            return False
        if "replacement" in row:
            replacement = row["replacement"]
            if replacement is not None and (type(replacement) is not dict
                    or set(replacement) != {"contributor", "summary"}
                    or not _credit_profile(replacement["contributor"])
                    or type(replacement["summary"]) is not str):
                return False
        if ("corrects" in row and (type(row["corrects"]) is not str
                or _WORKSPACE_DIGEST.fullmatch(row["corrects"]) is None)) or (
                "previous" in row and row["previous"] is not None and
                (type(row["previous"]) is not str or _WORKSPACE_DIGEST.fullmatch(row["previous"]) is None)) or (
                "recorded_at" in row and type(row["recorded_at"]) is not str):
            return False
    return True


def validate_shader_doctor(operation: str, args: Mapping[str, Any]) -> None:
    """Validate the exact request identity before contacting the mounted Studio."""
    required = ({"request_id", "origin", "shader_id", "project_context_witness", "studio_surface_id"}
                if operation == "request" else {"request_id", "project_context_witness"})
    if not isinstance(args, Mapping) or set(args) != required:
        raise HextileClientError("Expected closed Shader Doctor arguments", kind="other", status_code=422)
    request_id = args["request_id"]
    try:
        valid_id = type(request_id) is str and str(uuid.UUID(request_id)) == request_id
    except (ValueError, AttributeError):
        valid_id = False
    if not valid_id or any(type(args[key]) is not str or not 1 <= len(args[key]) <= 256
                           for key in required - {"request_id"}):
        raise HextileClientError("Invalid Shader Doctor request identity", kind="other", status_code=422)
    if operation == "request" and (args["origin"] not in {"builtin", "user", "project"}
                                   or len(args["shader_id"]) > 128):
        raise HextileClientError("Invalid Shader Doctor shader identity", kind="other", status_code=422)


def validate_shader_workspace(operation: str, args: Mapping[str, Any]) -> None:
    """Closed transport admission; APP owns writer identity, replay and saved-base checks."""
    def refuse(message: str = "Expected closed Shader workspace arguments") -> None:
        raise HextileClientError(message, kind="other", status_code=422)

    def text(value: Any, maximum: int = 256) -> bool:
        return type(value) is str and 1 <= len(value) <= maximum

    def digest(value: Any) -> bool:
        return type(value) is str and _WORKSPACE_DIGEST.fullmatch(value) is not None

    if not isinstance(args, Mapping):
        refuse()
    if operation == "open":
        required = {"shader", "project_context_witness", "expected_working_revision",
                    "expected_document_hash", "expected_source_hash", "studio_surface_id"}
        base = {"expected_working_revision", "expected_document_hash", "expected_source_hash"}
        supplied = base & args.keys()
        if (not required - base <= args.keys()
                or args.keys() - required - {"existing_workspace", "workspace_schema", "attribution_schema"}
                or ("workspace_schema" in args and (type(args["workspace_schema"]) is not int or args["workspace_schema"] != 2))
                or ("attribution_schema" in args and (type(args["attribution_schema"]) is not int or args["attribution_schema"] != 1))
                or (supplied and supplied != base)
                or (args.get("workspace_schema") != 2 and supplied != base)):
            refuse()
        shader = args["shader"]
        if (type(shader) is not dict or set(shader) != {"origin", "shaderId"}
                or shader["origin"] not in ("project", "user") or not text(shader["shaderId"], 128)
                or re.fullmatch(r"[A-Za-z0-9_-]+", shader["shaderId"]) is None
                or not text(args["project_context_witness"]) or not text(args["studio_surface_id"])
                or (supplied and (type(args["expected_working_revision"]) is not int or args["expected_working_revision"] < 1
                                 or not digest(args["expected_document_hash"]) or not digest(args["expected_source_hash"])))):
            refuse()
        if "existing_workspace" in args:
            adopt = args["existing_workspace"]
            if (type(adopt) is not dict or set(adopt) != {"action", "expected_content_digest"}
                    or adopt["action"] != "adopt" or not digest(adopt["expected_content_digest"])):
                refuse()
        return
    required = {"handle", "change_id", "expected_generation", "content_digest"} if operation == "register" else {"handle", "change_id", "project_context_witness"}
    optional = {"include_source_diagnostics"} if operation == "get" else (
        {"attribution_action", "source_proposal"} if operation == "register" else set())
    if (operation not in {"register", "get"} or not required <= args.keys()
            or args.keys() - required - optional
            or ("include_source_diagnostics" in args and type(args["include_source_diagnostics"]) is not bool)
            or ("attribution_action" in args and args["attribution_action"] not in {"include", "skip_optional"})):
        refuse()
    handle, change_id = args["handle"], args["change_id"]
    if type(handle) is not str or _WORKSPACE_HANDLE.fullmatch(handle) is None:
        refuse("Workspace handle must be opaque ASCII of at most 64 characters")
    # Bound the string and decimal before integer conversion, including namespace.
    if type(change_id) is not str or len(change_id) > 81 or not change_id.startswith(handle + ":"):
        suffix = ""
    else:
        suffix = change_id[len(handle) + 1:]
    if _WORKSPACE_SUFFIX.fullmatch(suffix) is None or int(suffix) > MAX_WORKSPACE_GENERATION:
        raise HextileClientError("generation_conflict: use <handle>:<positive canonical generation>",
                                 kind="http", status_code=409,
                                 receipt={"code": "generation_conflict"})
    if operation == "register":
        if (type(args["expected_generation"]) is not int
                or not 0 <= args["expected_generation"] < MAX_WORKSPACE_GENERATION
                or not digest(args["content_digest"])
                or ("source_proposal" in args and not _credit_source_proposal(args["source_proposal"]))):
            refuse()
        # APP compares suffix to expected_generation+1 after checking retained replay,
        # so altered retained inputs keep their authoritative idempotency_conflict.
    elif not text(args["project_context_witness"]):
        refuse()


def _layer_transport_unknown(exc: BaseException) -> bool:
    return isinstance(exc, http.client.HTTPException) or (
        isinstance(exc, HextileClientError) and exc.kind == "app_down"
    )


class HextileClientError(RuntimeError):
    """HTTP or transport failure talking to the local backend."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        body: Optional[str] = None,
        kind: str = "http",
        receipt: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.kind = kind  # app_down | upgrade | http | other
        self.receipt = dict(receipt) if receipt is not None else None


_SHADER_SEQUENCE_REQUIRED = {
    "shader_ref", "project_context_witness", "working_revision", "document_hash",
    "source_hash", "idempotency_key", "name", "frame_rate", "frame_count",
    "start_time", "end_time", "width", "height", "seed", "output",
}
_SHADER_SEQUENCE_OPTIONAL = {"resource_manifest_hash", "selected_resource_frames",
                             "supersampling", "folder_export", "publication_mode"}


def _native_folder_intent(value: Any) -> bool:
    if type(value) is not dict or not {"destination_folder", "format"} <= set(value) <= {
            "destination_folder", "format", "quality_if_jpg"}:
        return False
    folder, encoding, quality = value["destination_folder"], value["format"], value.get("quality_if_jpg")
    return (type(folder) is str and 1 <= len(folder) <= 4096 and _absolute_task_path(folder)
            and "\x00" not in folder
            and encoding in {"PNG", "JPG"}
            and ((encoding == "JPG" and type(quality) is int and 1 <= quality <= 100)
                 or (encoding == "PNG" and quality is None)))


def _same_native_intent(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (left["destination_folder"] == right["destination_folder"]
            and left["format"] == right["format"]
            and left.get("quality_if_jpg") == right.get("quality_if_jpg"))


def _native_observation(value: Any) -> dict[str, Any] | None:
    if type(value) is not dict or len(value) > 16:
        return None
    out: dict[str, Any] = {}
    for key, pattern in (("run_id", r"[0-9a-f]{32}"),
                         ("phase", r"[a-z][a-z_]{0,31}"),
                         ("attempt_id", r"attempt_[0-9a-f]{32}"),
                         ("observed_at", r"[0-9T:+.Z-]{10,48}")):
        item = value.get(key)
        if type(item) is str and re.fullmatch(pattern, item):
            out[key] = item
    for key in ("revision", "verified_cursor", "sample_count", "active_elapsed_ms",
                "phase_elapsed_ms", "checked_count", "check_total"):
        item = value.get(key)
        if type(item) is int and item >= 0:
            out[key] = item
    index = value.get("active_frame_index")
    if index is None and "active_frame_index" in value:
        out["active_frame_index"] = None
    elif type(index) is int and index >= 0:
        out["active_frame_index"] = index
    fraction = value.get("frame_fraction")
    if fraction is None and "frame_fraction" in value:
        out["frame_fraction"] = None
    elif type(fraction) in (int, float) and math.isfinite(fraction) and 0 <= fraction <= 1:
        out["frame_fraction"] = fraction
    durations = value.get("durations_ms")
    if type(durations) is list and len(durations) <= 8 and all(type(item) is int and item >= 0 for item in durations):
        out["durations_ms"] = list(durations)
    return out if "run_id" in out and "revision" in out and "phase" in out else None


def _native_sequence_fields(data: Mapping[str, Any]) -> dict[str, Any]:
    """Bounded native evidence common to both producers; missing old-peer fields stay absent."""
    out: dict[str, Any] = {}
    if type(data.get("producer")) is str and data["producer"] in {"shader", "fractal"}:
        out["producer"] = data["producer"]
    if type(data.get("name")) is str and len(data["name"]) <= 128:
        out["name"] = data["name"]
    source = data.get("shader_source") if data.get("producer") == "shader" else data.get("fractal_source")
    if type(source) is dict:
        safe_source: dict[str, Any] = {}
        if data.get("producer") == "shader":
            for key in ("origin", "id"):
                if type(source.get(key)) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", source[key]):
                    safe_source[key] = source[key]
            if type(source.get("working_revision")) is int and source["working_revision"] >= 1:
                safe_source["working_revision"] = source["working_revision"]
            for key in ("document_hash", "source_hash", "resource_manifest_hash", "render_identity"):
                if type(source.get(key)) is str and _WORKSPACE_DIGEST.fullmatch(source[key]):
                    safe_source[key] = source[key]
        else:
            if type(source.get("scene_id")) is str and re.fullmatch(r"scn_[0-9a-f]{8}", source["scene_id"]):
                safe_source["scene_id"] = source["scene_id"]
            for key in ("scene_revision", "document_hash", "render_identity"):
                if type(source.get(key)) is str and _WORKSPACE_DIGEST.fullmatch(source[key]):
                    safe_source[key] = source[key]
        if safe_source:
            out["source"] = safe_source
    if type(data.get("error")) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,127}", data["error"]):
        out["error"] = data["error"]
    if type(data.get("ownership_live")) is bool:
        out["ownership_live"] = data["ownership_live"]
    for key in ("render_files_available", "storage_available"):
        if type(data.get(key)) is bool:
            out[key] = data[key]
    observation = _native_observation(data.get("render_observation"))
    if observation is not None:
        out["render_observation"] = observation
    receipt = data.get("continuation_receipt")
    if type(receipt) is dict and len(receipt) <= 8:
        projected = {}
        for key in ("key", "request_hash", "inspection_fingerprint", "run_id", "mode"):
            value = receipt.get(key)
            pattern = (r"sha256:[0-9a-f]{64}" if key in {"request_hash", "inspection_fingerprint"}
                       else r"[0-9a-f]{32}" if key == "run_id"
                       else r"[a-z_]{1,32}" if key == "mode"
                       else r"[^\x00-\x1f]{1,128}")
            if type(value) is str and re.fullmatch(pattern, value):
                projected[key] = value
        if {"key", "request_hash", "inspection_fingerprint", "run_id"} <= set(projected):
            out["continuation_receipt"] = projected
    storage = data.get("storage")
    if type(storage) is dict and storage.get("layout") in {"direct", "legacy", "deferred"}:
        safe = {"layout": storage["layout"]}
        if storage.get("ownership") in {"generated", "borrowed"}:
            safe["ownership"] = storage["ownership"]
        encoding = storage.get("encoding")
        if type(encoding) is dict and encoding.get("format") in {"PNG", "JPG"}:
            safe["encoding"] = {"format": encoding["format"], "quality_if_jpg": encoding.get("quality_if_jpg")}
        out["storage"] = safe
    settings = data.get("accepted_settings")
    if type(settings) is dict and len(settings) <= 20:
        safe_settings: dict[str, Any] = {}
        for key in ("name", "quality"):
            if type(settings.get(key)) is str and len(settings[key]) <= 128:
                safe_settings[key] = settings[key]
        for key in ("frame_count", "width", "height", "seed", "source_width", "source_height",
                    "output_width", "output_height"):
            if type(settings.get(key)) is int and settings[key] >= 0:
                safe_settings[key] = settings[key]
        if type(settings.get("supersampling")) in (int, float) and math.isfinite(settings["supersampling"]):
            safe_settings["supersampling"] = settings["supersampling"]
        rate = settings.get("frame_rate")
        if type(rate) is dict and set(rate) == {"num", "den"} and all(type(rate[key]) is int and rate[key] > 0 for key in rate):
            safe_settings["frame_rate"] = dict(rate)
        for key in ("start_time", "end_time"):
            value = settings.get(key)
            if type(value) is dict and set(value) == {"num", "den"} and all(
                    type(value[part]) is str and re.fullmatch(r"[0-9]{1,32}", value[part]) for part in value):
                safe_settings[key] = dict(value)
        output = settings.get("output")
        if type(output) is dict and output.get("projection") in {"equirectangular", "fulldome", "fulldome_angular"}:
            projected = {"projection": output["projection"]}
            for key in ("diameter", "fov_deg", "pan", "tilt", "roll"):
                value = output.get(key)
                if type(value) in (int, float) and math.isfinite(value):
                    projected[key] = value
            safe_settings["output"] = projected
        destination = settings.get("destination_intent")
        if _native_folder_intent(destination):
            safe_settings["destination_intent"] = {"format": destination["format"],
                                                    "quality_if_jpg": destination.get("quality_if_jpg")}
        out["accepted_settings"] = safe_settings
    return out


def _native_inspection_result(data: Any, producer: str) -> dict[str, Any]:
    if type(data) is not dict or data.get("status") not in {
            "new", "unfinished", "completed", "unavailable", "conflict"}:
        raise HextileClientError("Invalid native destination inspection", kind="other")
    result: dict[str, Any] = {"status": data["status"]}
    if type(data.get("code")) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,127}", data["code"]):
        result["code"] = data["code"]
    if data["status"] in {"new", "unavailable", "conflict"}:
        return result
    required = ("sequence_id", "producer", "render_identity", "recipe_hash", "destination_folder",
                "format", "frames_completed", "frame_count", "native_status", "publication_state",
                "inspection_fingerprint")
    if (not all(key in data for key in required) or data["producer"] != producer
            or type(data["sequence_id"]) is not str or re.fullmatch(r"seq_[0-9a-f]{32}", data["sequence_id"]) is None
            or any(type(data[key]) is not str or _WORKSPACE_DIGEST.fullmatch(data[key]) is None
                   for key in ("render_identity", "recipe_hash", "inspection_fingerprint"))
            or not _absolute_task_path(data["destination_folder"])
            or len(data["destination_folder"]) > 4096
            or data["format"] not in {"PNG", "JPG"}
            or any(type(data[key]) is not int or data[key] < 0 for key in ("frames_completed", "frame_count"))
            or data["frames_completed"] > data["frame_count"]
            or data["publication_state"] not in {"direct", "admitted", "not_admitted", "legacy"}
            or type(data["native_status"]) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", data["native_status"]) is None):
        raise HextileClientError("Invalid native destination inspection", kind="other")
    quality = data.get("quality_if_jpg")
    if (data["format"] == "JPG" and (type(quality) is not int or not 1 <= quality <= 100)
            or data["format"] == "PNG" and quality is not None):
        raise HextileClientError("Invalid native destination encoding", kind="other")
    result.update({key: data[key] for key in required if key != "destination_folder"})
    result["quality_if_jpg"] = quality
    for key, pattern in (("attempt_id", r"attempt_[0-9a-f]{32}"),):
        if data.get(key) is None and key in data:
            result[key] = None
        elif type(data.get(key)) is str and re.fullmatch(pattern, data[key]):
            result[key] = data[key]
        elif key in data:
            raise HextileClientError("Invalid native destination attempt", kind="other")
    if data.get("attempt_revision") is None and "attempt_revision" in data:
        result["attempt_revision"] = None
    elif type(data.get("attempt_revision")) is int and data["attempt_revision"] >= 0:
        result["attempt_revision"] = data["attempt_revision"]
    elif "attempt_revision" in data:
        raise HextileClientError("Invalid native destination attempt revision", kind="other")
    if type(data.get("ownership_live")) is bool:
        result["ownership_live"] = data["ownership_live"]
    elif "ownership_live" in data:
        raise HextileClientError("Invalid native destination ownership", kind="other")
    # The caller keeps its immutable selected locator; never echo APP absolute paths.
    return result


def validate_shader_sequence_request(body: Mapping[str, Any]) -> None:
    """Closed transport guard; APP remains authoritative for saved identity and resources."""
    def refuse() -> None:
        raise HextileClientError("Expected a closed saved-native Shader sequence request", kind="other", status_code=422)

    def integer(value: Any, lo: int, hi: int) -> bool:
        return type(value) is int and lo <= value <= hi

    def text(value: Any, maximum: int) -> bool:
        return type(value) is str and 1 <= len(value) <= maximum

    def digest(value: Any) -> bool:
        return type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None

    def rational(value: Any) -> Fraction:
        if (type(value) is not dict or set(value) != {"num", "den"}
                or any(type(value[key]) is not str or re.fullmatch(
                    r"(0|[1-9][0-9]{0,31})" if key == "num" else r"[1-9][0-9]{0,31}",
                    value[key]) is None for key in ("num", "den"))):
            refuse()
        result = Fraction(int(value["num"]), int(value["den"]))
        if result.denominator != int(value["den"]):
            refuse()
        return result

    if (not isinstance(body, Mapping) or not _SHADER_SEQUENCE_REQUIRED <= set(body)
            or set(body) - _SHADER_SEQUENCE_REQUIRED - _SHADER_SEQUENCE_OPTIONAL):
        refuse()
    mode = body.get("publication_mode")
    folder = body.get("folder_export")
    if (mode not in (None, "deferred")
            or (mode == "deferred") != (folder is None)
            or (folder is not None and not _native_folder_intent(folder))):
        refuse()
    scale = body.get("supersampling", 1.0)
    if (type(scale) not in (int, float) or not math.isfinite(scale)
            or not 100 <= round(scale * 100) <= 200
            or abs(scale * 100 - round(scale * 100)) > 1e-8):
        refuse()
    ref = body["shader_ref"]
    if (type(ref) is not dict or set(ref) != {"origin", "id"}
            or ref["origin"] not in ("builtin", "user", "project")
            or type(ref["id"]) is not str or re.fullmatch(r"[a-zA-Z0-9_-]+", ref["id"]) is None):
        refuse()
    if (not text(body["project_context_witness"], 256) or not text(body["idempotency_key"], 128)
            or not text(body["name"], 128) or not integer(body["working_revision"], 1, 2**63 - 1)
            or not digest(body["document_hash"]) or not digest(body["source_hash"])):
        refuse()
    if "resource_manifest_hash" in body and body["resource_manifest_hash"] is not None and not digest(body["resource_manifest_hash"]):
        refuse()
    frames = body.get("selected_resource_frames")
    if frames is not None:
        if type(frames) is not list:
            refuse()
        for frame in frames:
            if (type(frame) is not dict or set(frame) != {"slot_id", "frame_hash", "index", "width", "height"}
                    or not text(frame["slot_id"], 256) or not digest(frame["frame_hash"])
                    or not integer(frame["index"], 0, 2**31 - 1)
                    or not integer(frame["width"], 1, 2**31 - 1)
                    or not integer(frame["height"], 1, 2**31 - 1)):
                refuse()
    rate = body["frame_rate"]
    if (type(rate) is not dict or set(rate) != {"num", "den"}
            or not integer(rate["num"], 1, 1_000_000) or not integer(rate["den"], 1, 1_000_000)):
        refuse()
    fps = Fraction(rate["num"], rate["den"])
    if fps.denominator != rate["den"] or not 1 <= fps <= 120:
        refuse()
    start, end = rational(body["start_time"]), rational(body["end_time"])
    count = (end - start) * fps
    expected_count = -(-count.numerator // count.denominator)
    if (not 0 <= start < end <= 86400 or not integer(body["frame_count"], 1, 10000)
            or body["frame_count"] != expected_count or not integer(body["seed"], 0, 2**32 - 1)
            or not integer(body["width"], 4, 16384) or not integer(body["height"], 2, 8192)):
        refuse()
    output = body["output"]
    if type(output) is not dict or "projection" not in output:
        refuse()
    projection = output["projection"]
    if projection == "equirectangular":
        if (set(output) != {"projection", "pan", "tilt", "roll"}
                or any(type(output[key]) not in (int, float) or output[key] != 0 for key in ("pan", "tilt", "roll"))
                or body["width"] != 2 * body["height"] or body["height"] % 2):
            refuse()
    elif projection in ("fulldome", "fulldome_angular"):
        if (set(output) != {"projection", "diameter", "fov_deg", "pan", "tilt", "roll"}
                or type(output["diameter"]) is not int or output["diameter"] not in (1024, 2048, 4096, 8192)
                or body["width"] != output["diameter"] or body["height"] != output["diameter"]):
            refuse()
        for key, lo, hi in (("fov_deg", 10, 360), ("pan", -180, 180), ("tilt", -90, 90), ("roll", -180, 180)):
            value = output[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
                refuse()
    else:
        refuse()


# Transport shape only. The APP store alone resolves references, checks domains/current ownership,
# and materializes a canonical candidate; this proxy never generates IDs or replays edits.
_SHADER_EDIT_FIELDS = {
    "add_source": ({"definition"}, {"ref"}), "remove_source": ({"source"}, set()),
    "set_label": ({"source", "label"}, set()), "install_wave": ({"source", "wave"}, set()),
    "set_expression": ({"source", "source_text"}, set()),
    "set_setting": ({"source", "setting", "value"}, set()),
    "set_period_unit": ({"source", "period_unit"}, set()),
    "set_click": ({"source", "button", "mode"}, set()), "rename_alias": ({"source", "alias"}, set()),
    "set_source_enabled": ({"source", "enabled"}, set()), "add_binding": ({"binding"}, {"ref"}),
    "update_binding": ({"binding", "value"}, set()), "remove_binding": ({"binding"}, set()),
    "set_binding_enabled": ({"binding", "enabled"}, set()), "set_mouse_input": ({"value"}, set()),
    "set_master_clock": ({"value"}, set()),
}
_SHADER_EDIT_FIELDS_V2 = {
    **_SHADER_EDIT_FIELDS,
    "set_parameter_expression": ({"target", "source_text", "refs"}, set()),
    "remove_parameter_expression": ({"target"}, set()),
    "set_parameter_mode": ({"target", "mode"}, {"binding"}),
    "set_timeline": ({"start", "end", "loop"}, set()),
}


def validate_shader_proposal(body: Mapping[str, Any]) -> None:
    """Reject foreign/XOR/oversized transport bodies before a local HTTP request."""
    def refuse() -> None:
        raise HextileClientError("Expected a closed Shader proposal", kind="other")

    if not isinstance(body, Mapping):
        refuse()
    kind = body.get("kind")
    if kind == "shader_document_candidate":
        alternatives = set(body) & {"complete_candidate", "source_edit", "modulation_edits"}
        if len(alternatives) != 1:
            refuse()
        field = next(iter(alternatives))
        if set(body) != {"kind", "base", "explanation", field} or type(body[field]) is not dict:
            refuse()
        if field == "modulation_edits":
            batch = body[field]
            if (set(batch) != {"schema", "edits"} or type(batch["schema"]) is not int
                    or batch["schema"] not in (1, 2) or type(batch["edits"]) is not list or len(batch["edits"]) > 32):
                refuse()
            try:
                size = len(json.dumps(batch, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))
            except (TypeError, ValueError, UnicodeError, RecursionError):
                refuse()
            if size > 65536:
                refuse()
            for edit in batch["edits"]:
                fields = _SHADER_EDIT_FIELDS if batch["schema"] == 1 else _SHADER_EDIT_FIELDS_V2
                if type(edit) is not dict or type(edit.get("op")) is not str or edit["op"] not in fields:
                    refuse()
                required, optional = fields[edit["op"]]
                if not (required | {"op"}) <= edit.keys() or edit.keys() - required - optional - {"op"}:
                    refuse()
    elif kind == "shader_variation_board":
        if set(body) != {"kind", "base", "board_id", "candidates"}:
            refuse()
    else:
        refuse()


class Client:
    """Sync HTTP wrapper around local APP routes (stdlib urllib)."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        opener: Any = None,
        internal_mode: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Injectable for tests (callable urlopen or opener.open).
        self._opener = opener
        self.internal_mode = internal_mode

    @contextmanager
    def request_headers(self, headers: Mapping[str, str]):
        """Bind private headers to one tools/call execution context."""
        token = _REQUEST_HEADERS.set(dict(headers))
        try:
            yield
        finally:
            _REQUEST_HEADERS.reset(token)

    def call_hextile_api(self, args: Mapping[str, Any]) -> Any:
        """One validated native JSON request, with the client's configured caller identity."""
        if (not isinstance(args, Mapping) or not {"method", "path"} <= args.keys()
                or set(args) - {"method", "path", "query", "body"}):
            raise HextileClientError("Expected method/path and optional query/body", kind="other", status_code=422)
        method, path = args["method"], args["path"]
        if (type(method) is not str or method not in {"GET", "POST", "PATCH", "PUT", "DELETE"}
                or type(path) is not str or not (path.startswith("/api/") or method == "GET" and path == "/openapi.json")
                or "\\" in path or any(ord(ch) < 33 for ch in path)
                or urllib.parse.urlsplit(path).path != path
                or any(part in {".", ".."} for part in path.split("/"))
                or "query" in args and type(args["query"]) is not dict):
            raise HextileClientError("Expected a relative native API path and supported method", kind="other", status_code=422)
        try:
            json.dumps(args.get("body"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise HextileClientError("Expected a JSON body", kind="other", status_code=422) from exc
        return self.request_json(method, path, args.get("body"), params=args.get("query"))

    # ── low-level ───────────────────────────────────────────────────────

    def request_json(
        self,
        method: str,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        """HTTP JSON request. Raises HextileClientError on failure."""
        url = self._url(path)
        if params:
            qs = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
            if qs:
                url = url + ("&" if "?" in url else "?") + qs
        data: Optional[bytes] = None
        req_headers = {"Accept": "application/json", **_REQUEST_HEADERS.get()}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        if headers:
            req_headers.update(dict(headers))
        # The APP gate must see every proxy request, including private Copilot calls.
        for key in tuple(req_headers):
            if key.lower() == "x-hextile-agent":
                del req_headers[key]
        req_headers["X-Hextile-Agent"] = "mcp"
        req = urllib.request.Request(
            url, data=data, headers=req_headers, method=method
        )
        to = self.timeout if timeout is None else timeout
        try:
            if self._opener is not None:
                resp_cm = self._opener(req, timeout=to)
            else:
                resp_cm = urllib.request.urlopen(req, timeout=to)
            with resp_cm as resp:
                raw = resp.read()
                code = getattr(resp, "status", None) or resp.getcode()
                if not raw:
                    return None
                try:
                    return json.loads(raw.decode("utf-8"))
                except ValueError as exc:
                    snippet = raw[:_ERROR_BODY_SNIPPET].decode("utf-8", "replace")
                    raise HextileClientError(
                        f"Invalid JSON from {path}: {snippet}",
                        status_code=code,
                        body=snippet,
                        kind="other",
                    ) from exc
        except HextileClientError:
            raise
        except urllib.error.HTTPError as exc:
            snippet = ""
            try:
                # Hotkeys has bounded structured conflict details, not a log snippet.
                limit = 64 * 1024 if path == "/api/agent/hotkeys/requests" or path.startswith("/api/agent/shader-workspaces/") else _ERROR_BODY_SNIPPET
                snippet = (exc.read(limit) or b"").decode(
                    "utf-8", "replace"
                )
            except Exception:
                snippet = str(exc.reason or "")
            if exc.code == 404 and "/api/workflows/run" in path:
                raise HextileClientError(
                    UPGRADE_MSG,
                    status_code=404,
                    body=snippet,
                    kind="upgrade",
                ) from exc
            if "/api/batch-workflows" in path:
                blob = snippet.lower()
                if exc.code == 409 and "batch_unavailable" in blob:
                    raise HextileClientError(
                        BATCH_UNAVAILABLE_MSG,
                        status_code=409,
                        body=snippet,
                        kind="capability",
                    ) from exc
                if exc.code == 404 and not any(code in blob for code in _BATCH_KNOWN_404):
                    raise HextileClientError(
                        BATCH_UNAVAILABLE_MSG,
                        status_code=404,
                        body=snippet,
                        kind="capability",
                    ) from exc
            raise HextileClientError(
                f"HTTP {exc.code} {method} {path}: {snippet}",
                status_code=exc.code,
                body=snippet,
                kind="http",
            ) from exc
        except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError, OSError) as exc:
            raise HextileClientError(APP_DOWN_MSG, status_code=None, body=str(exc), kind="app_down") from exc

    def request_shader_preview_image(self, request_id: str, params: Mapping[str, Any]) -> bytes | dict:
        """Explicit pixel opt-in; bytes never enter a JSON result."""
        path = "/api/shaders/agent-operations/output/preview/" + request_id
        url = self._url(path) + "?" + urllib.parse.urlencode({**params, "image": "true"})
        headers = {**_REQUEST_HEADERS.get(), "X-Hextile-Agent": "mcp", "Accept": "image/png"}
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            cm = self._opener(req, timeout=self.timeout) if self._opener is not None else urllib.request.urlopen(req, timeout=self.timeout)
            with cm as response:
                data = response.read(8 * 1024 * 1024 + 1)
                if len(data) > 8 * 1024 * 1024:
                    raise HextileClientError("Shader image exceeds bounded output", status_code=413, kind="other")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if content_type == "image/png":
                    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise HextileClientError("Invalid Shader image bytes", status_code=502, kind="other")
                    return data
                if content_type == "application/json":
                    try:
                        result = json.loads(data.decode("utf-8"))
                    except (UnicodeError, ValueError) as exc:
                        raise HextileClientError("Invalid Shader image response", status_code=502,
                                                 kind="other") from exc
                    result = _shader_output_receipt("get_preview", {"request_id": request_id}, result)
                    if result["state"] in {"pending", "unavailable"}:
                        return result
                raise HextileClientError("Invalid Shader image response", status_code=502, kind="other")
        except HextileClientError:
            raise
        except urllib.error.HTTPError as exc:
            raise HextileClientError("Shader image unavailable", status_code=exc.code,
                                     body=(exc.read(800) or b"").decode("utf-8", "replace"), kind="http") from exc
        except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError, OSError) as exc:
            raise HextileClientError(APP_DOWN_MSG, status_code=None, body=str(exc), kind="app_down") from exc

    def hotkeys_request(self, op: str, args: Mapping[str, Any]) -> Any:
        """Proxy the frontend-owned profile once; never replay an uncertain write."""
        mutating = op not in {"list", "inspect"}
        unknown_message = "Hotkeys outcome unknown; read the profile before approving another mutation."
        try:
            result = self.request_json(
                "POST", "/api/agent/hotkeys/requests", {"op": op, "args": dict(args)},
                timeout=30.0,
                headers=None if self.internal_mode else {"X-Hextile-Agent": "mcp"},
            )
            if not isinstance(result, dict) or result.get("ok") is not True or not isinstance(result.get("data"), dict):
                raise HextileClientError("Invalid Hotkeys acknowledgement", kind="other", status_code=200)
            return result["data"]
        except http.client.HTTPException as exc:
            raise HextileClientError(
                unknown_message if mutating else APP_DOWN_MSG,
                kind="hotkeys_outcome_unknown" if mutating else "app_down",
            ) from exc
        except HextileClientError as exc:
            try:
                detail = json.loads(exc.body or "{}").get("detail", {})
            except (ValueError, AttributeError):
                detail = {}
            if not isinstance(detail, dict):
                detail = {}
            code = detail.get("code")
            malformed_success = exc.kind == "other" and exc.status_code is not None and 200 <= exc.status_code < 300
            if mutating and (code == "outcome_unknown" or exc.kind == "app_down" or malformed_success):
                raise HextileClientError(unknown_message, kind="hotkeys_outcome_unknown", status_code=exc.status_code) from exc
            if isinstance(code, str):
                recovery = {
                    "stale_revision": "Read the profile again before proposing a new edit.",
                    "hotkey_conflict": "Inspect conflicts and resolve each action explicitly.",
                    "hotkeys_app_unavailable": "Open the app and read the profile again.",
                    "unsupported_hotkey_profile": "Only an explicitly approved reset can replace a future profile.",
                }.get(code, "Read or inspect Hotkeys before another edit.")
                raise HextileClientError(
                    f"{code}: {recovery}", status_code=exc.status_code, kind=exc.kind,
                    receipt={key: detail[key] for key in ("code", "conflicts", "request_id") if key in detail},
                ) from exc
            raise

    def get_json(
        self,
        path: str,
        *,
        timeout: Optional[float] = None,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        return self.request_json("GET", path, timeout=timeout, params=params, headers=headers)

    def post_json(
        self,
        path: str,
        body: Optional[Mapping[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        return self.request_json(
            "POST", path, body, timeout=timeout, params=params, headers=headers
        )

    def delete_json(
        self,
        path: str,
        *,
        timeout: Optional[float] = None,
    ) -> Any:
        return self.request_json("DELETE", path, timeout=timeout)

    def post_activity(self, envelope: Mapping[str, Any]) -> Any:
        """POST /api/agent/events — 1s timeout. Caller swallows errors."""
        return self.request_json(
            "POST", "/api/agent/events", envelope, timeout=1
        )

    @staticmethod
    def _canonical_uuid4(value: Any, *, field: str = "request_id") -> str:
        try:
            parsed = uuid.UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            parsed = None
        if parsed is None or str(parsed) != value or parsed.version != 4:
            raise HextileClientError(
                f"{field} must be a canonical UUID", kind="other", status_code=422,
            )
        return value

    @staticmethod
    def _local_file_path(value: Any) -> str:
        if type(value) is not str or not 1 <= len(value) <= 4096:
            raise HextileClientError("path must be an absolute native filesystem path", kind="other", status_code=422)
        return value

    def get_local_access_status(self) -> dict[str, Any]:
        """GET /api/agent/mcp-status even with MCP OFF and no Studio."""
        data = self.get_json("/api/agent/mcp-status")
        if type(data) is not dict:
            raise HextileClientError("Invalid MCP status", kind="other")
        if type(data.get("enabled")) is not bool:
            raise HextileClientError("Invalid MCP connection status", kind="other")
        return {"enabled": data["enabled"]}

    def local_file_stat(self, path: Any) -> Any:
        """GET /api/agent/local-files/stat."""
        return self.get_json(
            "/api/agent/local-files/stat",
            params={"path": self._local_file_path(path)},
        )

    def local_file_read(
        self,
        path: Any,
        *,
        expected_version: Any,
        offset: Any,
        max_bytes: Any,
        encoding: Any = None,
    ) -> Any:
        """GET /api/agent/local-files/read."""
        if type(expected_version) is not str or not 1 <= len(expected_version) <= 256:
            raise HextileClientError("expected_version is required", kind="other", status_code=422)
        if type(offset) is not int or offset < 0:
            raise HextileClientError("offset must be a non-negative integer", kind="other", status_code=422)
        if type(max_bytes) is not int or not 1 <= max_bytes <= 32768:
            raise HextileClientError("max_bytes must be 1..32768", kind="other", status_code=422)
        if encoding is not None and encoding not in {"utf-8", "base64"}:
            raise HextileClientError("encoding must be utf-8 or base64", kind="other", status_code=422)
        params: dict[str, Any] = {
            "path": self._local_file_path(path),
            "expected_version": expected_version,
            "offset": offset,
            "max_bytes": max_bytes,
        }
        if encoding is not None:
            params["encoding"] = encoding
        return self.get_json("/api/agent/local-files/read", params=params)

    def local_file_write_begin(
        self,
        *,
        request_id: Any,
        path: Any,
        mode: Any,
        expected_sha256: Any,
        total_bytes: Any,
        session_id: str,
    ) -> Any:
        """POST /api/agent/local-files/writes."""
        request_id = self._canonical_uuid4(request_id)
        if mode not in {"create", "replace"}:
            raise HextileClientError("mode must be create or replace", kind="other", status_code=422)
        if type(total_bytes) is not int or total_bytes < 0:
            raise HextileClientError("total_bytes must be a non-negative integer", kind="other", status_code=422)
        if mode == "create":
            if expected_sha256 is not None:
                raise HextileClientError("create requires expected_sha256 null", kind="other", status_code=422)
        elif type(expected_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
            raise HextileClientError("replace requires a 64-hex expected_sha256", kind="other", status_code=422)
        body = {
            "request_id": request_id,
            "path": self._local_file_path(path),
            "mode": mode,
            "expected_sha256": expected_sha256,
            "total_bytes": total_bytes,
        }
        return self.post_json(
            "/api/agent/local-files/writes",
            body,
            headers=self._shader_parameter_headers(session_id),
        )

    def local_file_write_append(
        self,
        *,
        write_id: Any,
        index: Any,
        data_base64: Any,
        session_id: str,
    ) -> Any:
        """POST /api/agent/local-files/writes/{write_id}/chunks."""
        if type(write_id) is not str or not 1 <= len(write_id) <= 128:
            raise HextileClientError("write_id is required", kind="other", status_code=422)
        if type(index) is not int or index < 0:
            raise HextileClientError("index must be a non-negative integer", kind="other", status_code=422)
        if type(data_base64) is not str or not 1 <= len(data_base64) <= 87384:
            raise HextileClientError("data_base64 must be a bounded Base64 chunk", kind="other", status_code=422)
        quoted = urllib.parse.quote(write_id, safe="")
        return self.post_json(
            f"/api/agent/local-files/writes/{quoted}/chunks",
            {"index": index, "data_base64": data_base64},
            headers=self._shader_parameter_headers(session_id),
        )

    def local_file_write_abort(self, write_id: Any, *, session_id: str) -> Any:
        """POST /api/agent/local-files/writes/{write_id}/abort."""
        if type(write_id) is not str or not 1 <= len(write_id) <= 128:
            raise HextileClientError("write_id is required", kind="other", status_code=422)
        quoted = urllib.parse.quote(write_id, safe="")
        return self.post_json(
            f"/api/agent/local-files/writes/{quoted}/abort",
            {},
            headers=self._shader_parameter_headers(session_id),
        )

    def local_file_write_commit(self, write_id: Any, *, session_id: str) -> Any:
        """POST /api/agent/local-files/writes/{write_id}/commit."""
        if type(write_id) is not str or not 1 <= len(write_id) <= 128:
            raise HextileClientError("write_id is required", kind="other", status_code=422)
        quoted = urllib.parse.quote(write_id, safe="")
        return self.post_json(
            f"/api/agent/local-files/writes/{quoted}/commit",
            {},
            headers=self._shader_parameter_headers(session_id),
        )

    def local_file_write_status(self, request_id: Any, *, session_id: str) -> Any:
        """GET /api/agent/local-files/writes/requests/{request_id} after trust or MCP OFF."""
        request_id = self._canonical_uuid4(request_id)
        quoted = urllib.parse.quote(request_id, safe="")
        data = self.get_json(
            f"/api/agent/local-files/writes/requests/{quoted}",
            headers=self._shader_parameter_headers(session_id),
        )
        if type(data) is not dict:
            raise HextileClientError(
                "Write outcome unknown. Read the original request_id; do not mint a new id.",
                kind="other",
                receipt={"request_id": request_id, "status": "outcome_unknown"},
            )
        allowed = ("request_id", "write_id", "status", "next_offset", "sha256", "size")
        return {key: data[key] for key in allowed if key in data}

    # ── workflows ───────────────────────────────────────────────────────

    def list_workflows(self) -> Any:
        """GET /api/workflows."""
        return self.get_json("/api/workflows")

    def get_workflow(self, origin: str, workflow_id: str) -> Any:
        """GET /api/workflows/{origin}/{id}."""
        o = urllib.parse.quote(origin, safe="")
        wid = urllib.parse.quote(workflow_id, safe="")
        return self.get_json(f"/api/workflows/{o}/{wid}")

    def get_capabilities(self) -> Any:
        """GET /api/workflows/capabilities."""
        return self.get_json("/api/workflows/capabilities")

    def _require_native_render(self, *, still_profile: str | None = None,
                               fractal_still_capture: bool = False) -> None:
        """New native semantics require an explicitly advertised peer contract."""
        try:
            capabilities = self.get_capabilities()
        except HextileClientError as exc:
            if exc.status_code == 404:
                raise HextileClientError("Native render contract unavailable on this APP peer",
                                         kind="other", status_code=501) from exc
            raise
        native = capabilities.get("native_render") if type(capabilities) is dict else None
        if (type(native) is not dict or native.get("contract") != "native-render/1"
                or type(native.get("sequences")) is not dict
                or type(native.get("stills")) is not dict
                or still_profile is not None and still_profile not in native["stills"]
                or fractal_still_capture and native.get("fractal_still_capture") != {
                    "protocol": "fractal_capture/1", "producer": "mounted_finished_preview",
                    "static_frame": True, "animated_sample": True}):
            raise HextileClientError("Native render contract unavailable on this APP peer",
                                     kind="other", status_code=501)

    def describe_image(self, body: Mapping[str, Any]) -> Any:
        """Ask APP to caption one exact local source; never open image bytes here."""
        return self.post_json(
            "/api/prompts/describe-source", body, timeout=LONG_OPERATION_TIMEOUT_S
        )

    def get_unreal_export_catalog(self) -> Any:
        return self.get_json("/api/renders/unreal-export/catalog")

    def preflight_unreal_export(self, render_id: str, body: Mapping[str, Any]) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        return self.post_json(f"/api/renders/{rid}/export/preflight", body)

    def preflight_file_export(self, render_id: str, body: Mapping[str, Any]) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        return self.post_json(f"/api/renders/{rid}/export/file-preflight", body)

    def export_render_file(self, render_id: str, body: Mapping[str, Any]) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        try:
            receipt = self.post_json(
                f"/api/renders/{rid}/export", body, timeout=LONG_OPERATION_TIMEOUT_S
            )
            destination = Path(str(body["destination"]))
            paths = receipt.get("paths") if isinstance(receipt, Mapping) else None
            expected_count = 6 if body.get("layout") == "six_faces" else 1
            valid_paths = (
                isinstance(paths, list)
                and len(paths) == expected_count
                and all(
                    isinstance(path, str)
                    and path
                    and Path(path).is_absolute()
                    and not path.endswith(("/", "\\"))
                    and Path(path).suffix
                    and Path(path).name == Path(path).name.rstrip(" .")
                    and not {".", ".."}.intersection(path.replace("\\", "/").split("/"))
                    for path in paths
                )
                and len({os.path.normcase(os.path.normpath(path)) for path in paths}) == expected_count
            )
            if (
                not isinstance(receipt, Mapping)
                or receipt.get("outcome") != "complete"
                or not valid_paths
                or (expected_count == 1 and paths[0] != str(destination))
                or (
                    expected_count == 6
                    and any(Path(path).parent != destination for path in paths)
                )
            ):
                raise HextileClientError(
                    "Export outcome unknown; inspect the destination before a new attempt.",
                    kind="file_outcome_unknown",
                )
            return receipt
        except http.client.HTTPException as exc:
            raise HextileClientError(
                "Export outcome unknown; inspect the destination before a new attempt.",
                body=str(exc),
                kind="file_outcome_unknown",
            ) from exc
        except HextileClientError as exc:
            malformed_2xx = (
                exc.kind == "other"
                and exc.status_code is not None
                and 200 <= exc.status_code < 300
            )
            if exc.kind == "app_down" or malformed_2xx:
                raise HextileClientError(
                    "Export outcome unknown; inspect the destination before a new attempt.",
                    status_code=exc.status_code,
                    body=None if malformed_2xx else exc.body,
                    kind="file_outcome_unknown",
                ) from exc
            raise

    def export_to_unreal_project(self, render_id: str, body: Mapping[str, Any]) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        payload = dict(body)
        payload.pop("destination", None)
        try:
            return self.post_json(
                f"/api/renders/{rid}/export",
                payload,
                timeout=LONG_OPERATION_TIMEOUT_S,
            )
        except HextileClientError as exc:
            if exc.kind == "app_down":
                raise HextileClientError(
                    "Connection ended; check the folder before retry.",
                    status_code=exc.status_code,
                    body=exc.body,
                    kind="ue_outcome_unknown",
                ) from exc
            raise

    # ── saved Layers generation ─────────────────────────────────────────

    def get_layer_draft(self, render_id: str, parent_id: str) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        return self.get_json(f"/api/renders/{rid}/layers/agent-state", params={"parent_id": parent_id})

    def generate_layer(self, render_id: str, body: Mapping[str, Any]) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        try:
            return self.post_json(f"/api/renders/{rid}/layers/agent-generate", body)
        except (HextileClientError, http.client.HTTPException) as exc:
            if not _layer_transport_unknown(exc):
                raise
            try:
                observed = self.get_layer_generation(render_id, str(body["request_id"]))
                if (isinstance(observed, Mapping) and observed.get("job_id") == body["request_id"]
                        and observed.get("parent_id") == body.get("parent_id")):
                    return {"job_id": observed["job_id"], "draft_id": observed.get("package_id"),
                            "composition_id": observed.get("composition_id"), "head": observed["parent_id"],
                            "state": observed.get("state", "unknown")}
            except (HextileClientError, http.client.HTTPException):
                pass
            raise HextileClientError(
                "Generation submission outcome unknown. Read get_layer_generation with the same request_id; "
                "a missing RAM job after restart is not permission to submit a new id.",
                kind="layer_outcome_unknown",
                receipt={"state": "unknown", "render_id": render_id, "request_id": body["request_id"],
                         "reconcile": "get_layer_generation"},
            ) from exc

    def get_layer_generation(self, render_id: str, job_id: str) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        jid = urllib.parse.quote(job_id, safe="")
        return self.get_json(f"/api/renders/{rid}/layers/generate/{jid}")

    def cancel_layer_generation(self, render_id: str, job_id: str) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        jid = urllib.parse.quote(job_id, safe="")
        return self.post_json(f"/api/renders/{rid}/layers/generate/{jid}/agent-cancel")

    def rematte_layer(self, render_id: str, job_id: str, body: Mapping[str, Any]) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        jid = urllib.parse.quote(job_id, safe="")
        try:
            return self.post_json(f"/api/renders/{rid}/layers/generate/{jid}/agent-rematte", body)
        except (HextileClientError, http.client.HTTPException) as exc:
            if not _layer_transport_unknown(exc):
                raise
            raise HextileClientError(
                "Re-matte outcome unknown and non-replayable: the server chooses its job id. "
                "Inspect local job activity before requesting a newly approved action.",
                kind="layer_outcome_unknown",
                receipt={"state": "unknown", "non_replayable": True, "render_id": render_id,
                         "parent_job_id": job_id},
            ) from exc

    def land_generated_layer(self, render_id: str, body: Mapping[str, Any]) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        try:
            return self.post_json(f"/api/renders/{rid}/layers/agent-land", body)
        except (HextileClientError, http.client.HTTPException) as exc:
            if not _layer_transport_unknown(exc):
                raise
            try:
                job = self.get_layer_generation(render_id, str(body["job_id"]))
                draft = self.get_layer_draft(render_id, str(body["expected_head"]))
                if (isinstance(job, Mapping) and job.get("state") == "ready"
                        and job.get("parent_id") == body["expected_head"]
                        and job.get("package_id") == body["draft_id"]
                        and job.get("composition_id") == body["composition_id"]
                        and isinstance(draft, Mapping) and draft.get("head") == body["expected_head"]
                        and draft.get("draft_id") == body["draft_id"]
                        and draft.get("composition_id") == body["composition_id"]):
                    for layer in draft.get("active_bag_layers", []):
                        if (isinstance(layer, Mapping) and layer.get("layer_id") == body["layer_id"]
                                and layer.get("asset") == job.get("asset")
                                and layer.get("recipeSource") == job.get("recipeSource")):
                            return {"draft_id": body["draft_id"], "composition_id": body["composition_id"],
                                    "mutation_rev": draft.get("mutation_rev"), "layer_id": body["layer_id"],
                                    "already_landed": True}
            except (HextileClientError, http.client.HTTPException):
                pass
            raise HextileClientError(
                "Layer landing outcome unknown. Inspect the exact saved draft and job before any repeat; "
                "never mint a new layer id to retry.",
                kind="layer_outcome_unknown",
                receipt={"state": "unknown", "render_id": render_id, "job_id": body["job_id"],
                         "layer_id": body["layer_id"], "draft_id": body["draft_id"],
                         "reconcile": "get_layer_draft and get_layer_generation"},
            ) from exc

    def commit_layer_draft(self, render_id: str, body: Mapping[str, Any]) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        try:
            return self.post_json(f"/api/renders/{rid}/layers/agent-commit", body, timeout=LONG_OPERATION_TIMEOUT_S)
        except (HextileClientError, http.client.HTTPException) as exc:
            if not _layer_transport_unknown(exc):
                raise
            try:
                rid = urllib.parse.quote(render_id, safe="")
                graph = self.get_json(f"/api/renders/{rid}/graph")
                if isinstance(graph, Mapping) and graph.get("head") == body["draft_id"]:
                    for node in graph.get("nodes", []):
                        if (isinstance(node, Mapping) and node.get("id") == body["draft_id"]
                                and node.get("op") == "layers" and node.get("parent") == body["parent_id"]):
                            return {"node_id": body["draft_id"], "head": body["draft_id"]}
            except (HextileClientError, http.client.HTTPException):
                pass
            raise HextileClientError(
                "Layer commit outcome unknown. Inspect the exact draft id in the render graph "
                "and HEAD before considering a new approval; do not replay blindly.",
                kind="layer_outcome_unknown",
                receipt={"state": "unknown", "render_id": render_id,
                         "draft_id": body["draft_id"], "parent_id": body["parent_id"],
                         "reconcile": "inspect render graph HEAD and draft node"},
            ) from exc

    def creative_live(self, tool_name: str, arguments: Mapping[str, Any]) -> Any:
        headers = _REQUEST_HEADERS.get()
        if not self.internal_mode or not headers.get("X-Hextile-Copilot-Token") or not headers.get("X-Hextile-Op"):
            raise HextileClientError("Live creative actions require an approved internal Copilot turn.",
                                     status_code=403, kind="http")
        try:
            return self.post_json("/api/agent/creative-live", {"tool_name": tool_name, "arguments": dict(arguments)})
        except (HextileClientError, http.client.HTTPException) as exc:
            if tool_name != "rematte_layer" or not _layer_transport_unknown(exc):
                raise
            raise HextileClientError(
                "Re-matte outcome unknown and non-replayable: the server chooses its job id. "
                "Inspect local job activity before requesting a newly approved action.",
                kind="layer_outcome_unknown",
                receipt={"state": "unknown", "non_replayable": True,
                         "render_id": arguments.get("render_id"), "parent_job_id": arguments.get("job_id")},
            ) from exc

    # ── saved Spot Clone ────────────────────────────────────────────────

    def preflight_spot_clone(self, render_id: str, parent_id: str) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        return self.get_json(f"/api/renders/{rid}/spot-clone/agent-preflight",
                             params={"parent_id": parent_id})

    def clone_spot(self, render_id: str, body: Mapping[str, Any]) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        try:
            result = self.post_json(f"/api/renders/{rid}/spot-clone/agent", body,
                                    timeout=LONG_OPERATION_TIMEOUT_S)
            if (not isinstance(result, Mapping) or result.get("node_id") != body["node_id"]
                    or result.get("state") != "complete"):
                raise HextileClientError("Spot Clone acknowledgement was incomplete",
                                         kind="spot_clone_outcome_unknown")
            return result
        except (HextileClientError, http.client.HTTPException) as exc:
            if not (_layer_transport_unknown(exc) or
                    isinstance(exc, HextileClientError) and exc.kind == "spot_clone_outcome_unknown"):
                raise
            raise HextileClientError(
                "Spot Clone outcome unknown. Read get_spot_clone with the same render_id "
                "and node_id; do not retry with a new id.",
                kind="spot_clone_outcome_unknown",
                receipt={"state": "unknown", "render_id": render_id,
                         "node_id": body["node_id"], "reconcile": "get_spot_clone"},
            ) from exc

    def get_spot_clone(self, render_id: str, node_id: str) -> Any:
        rid = urllib.parse.quote(render_id, safe="")
        nid = urllib.parse.quote(node_id, safe="")
        return self.get_json(f"/api/renders/{rid}/spot-clone/agent/{nid}")

    def apply_config_delta(
        self,
        *,
        config_partial: Mapping[str, Any],
        doc_generation: str,
        explanation: str = "",
    ) -> Any:
        """POST /api/agent/apply-live. No local merge. Never coerce {}."""
        if not isinstance(config_partial, Mapping):
            raise HextileClientError(
                "config_partial must be a JSON object",
                status_code=None,
                kind="other",
            )
        return self.post_json(
            "/api/agent/apply-live",
            {
                "config_partial": dict(config_partial),
                "doc_generation": str(doc_generation),
                "explanation": explanation,
            },
            headers={"X-Hextile-Agent": "mcp"},
        )

    def get_shader_context(
        self,
        *,
        origin: str,
        shader_id: str,
        project_context_witness: str,
        include_source: bool = False,
        include_formula: bool = False,
        working_revision: Optional[int] = None,
    ) -> Any:
        """GET /api/agent/shader-context. Metadata unless include_source is true."""
        if (origin not in ("builtin", "user", "project") or not shader_id or not project_context_witness
                or type(include_source) is not bool or type(include_formula) is not bool
                or (working_revision is not None and (type(working_revision) is not int or working_revision < 1))):
            raise HextileClientError(
                "origin, shader_id, and project_context_witness are required",
                status_code=None,
                kind="other",
            )
        params: dict[str, Any] = {
            "origin": origin,
            "shader_id": shader_id,
            "include_source": "true" if include_source else "false",
            "include_formula": "true" if include_formula else "false",
        }
        if working_revision is not None:
            params["working_revision"] = int(working_revision)
        return self.get_json(
            "/api/agent/shader-context",
            params=params,
            headers={
                "X-Hextile-Agent": "mcp",
                "X-Hextile-Project-Witness": project_context_witness,
            },
        )

    @staticmethod
    def _shader_parameter_headers(session_id: str) -> dict[str, str]:
        """The stdio proxy supplies this origin; tool arguments never do."""
        try:
            valid = type(session_id) is str and str(uuid.UUID(session_id)) == session_id
        except (ValueError, AttributeError, TypeError):
            valid = False
        if not valid:
            raise HextileClientError("Invalid MCP session origin", kind="other", status_code=422)
        return {"X-Hextile-Agent": "mcp", "X-Hextile-Mcp-Session": session_id}

    def get_shader_parameters(self, *, session_id: str) -> Any:
        """Read only the mounted Shader's source-free exposed controls."""
        return self.get_json("/api/agent/shader-parameters",
                             headers=self._shader_parameter_headers(session_id))

    def set_shader_parameter(self, args: Mapping[str, Any], *, session_id: str) -> Any:
        """Submit one witnessed value edit or reconcile its original request ID."""
        headers = self._shader_parameter_headers(session_id)
        request_id = args.get("client_request_id") if isinstance(args, Mapping) else None
        if type(request_id) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id) is None:
            raise HextileClientError("Invalid Shader parameter client_request_id", kind="other", status_code=422)
        operation = args.get("operation")
        if operation == "status":
            if set(args) != {"operation", "client_request_id"}:
                raise HextileClientError("Expected exact Shader parameter status arguments", kind="other", status_code=422)
            try:
                data = self.get_json(f"/api/agent/shader-parameter/requests/{request_id}",
                                     headers=headers)
            except HextileClientError as exc:
                if exc.status_code == 404:
                    raise HextileClientError(
                        f"Shader parameter outcome unknown for client_request_id={request_id}; absence is not refusal.",
                        kind="shader_parameter_outcome_unknown", status_code=404,
                        receipt={"client_request_id": request_id, "status": "unknown"}) from exc
                raise
            return self._shader_parameter_receipt(data, request_id, submit=False)
        if operation != "submit" or set(args) != {"operation", "client_request_id", "witness", "parameter_id", "value"}:
            raise HextileClientError("Expected exact Shader parameter submit arguments", kind="other", status_code=422)
        witness = args["witness"]
        if (type(witness) is not dict or set(witness) != {"studio_surface_id", "project_context_witness", "shader", "base", "edit_sequence"}
                or type(witness["studio_surface_id"]) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", witness["studio_surface_id"])
                or type(witness["project_context_witness"]) is not str or not 1 <= len(witness["project_context_witness"]) <= 256
                or type(witness["edit_sequence"]) is not int or not 0 <= witness["edit_sequence"] <= 2**53 - 1
                or type(witness["shader"]) is not dict or set(witness["shader"]) != {"origin", "shaderId"}
                or witness["shader"]["origin"] not in {"builtin", "user", "project"}
                or type(witness["shader"]["shaderId"]) is not str
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", witness["shader"]["shaderId"])):
            raise HextileClientError("Invalid Shader parameter witness", kind="other", status_code=422)
        base = witness["base"]
        digest = lambda value: type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None
        if type(base) is not dict:
            raise HextileClientError("Invalid Shader parameter base", kind="other", status_code=422)
        if base.get("kind") == "unaccepted":
            valid_base = set(base) == {"kind", "authoring_digest"} and digest(base["authoring_digest"])
        else:
            tagged = base.get("kind") == "saved"
            required = {"working_revision", "document_hash", "source_hash"} | ({"kind"} if tagged else set())
            valid_base = (required <= set(base) and set(base) <= (required | (set() if tagged else {"manifest_hash"}))
                          and type(base["working_revision"]) is int and base["working_revision"] >= 1
                          and digest(base["document_hash"]) and digest(base["source_hash"]))
            if valid_base and "manifest_hash" in base:
                valid_base = base["manifest_hash"] is None or digest(base["manifest_hash"])
        if not valid_base:
            raise HextileClientError("Invalid Shader parameter base", kind="other", status_code=422)
        if type(args["parameter_id"]) is not str or not 1 <= len(args["parameter_id"]) <= 128:
            raise HextileClientError("Invalid Shader parameter ID", kind="other", status_code=422)
        def finite_json(value: Any, depth: int = 0) -> bool:
            if depth > 8:
                return False
            if value is None or type(value) in (str, bool, int):
                return True
            if type(value) is float:
                return math.isfinite(value)
            if type(value) is list:
                return len(value) <= 64 and all(finite_json(item, depth + 1) for item in value)
            if type(value) is dict:
                return len(value) <= 64 and all(type(key) is str and finite_json(item, depth + 1)
                                                for key, item in value.items())
            return False
        value = args["value"]
        if not finite_json(value) or len(json.dumps(value, allow_nan=False).encode("utf-8")) > 65536:
            raise HextileClientError("Shader parameter value must be bounded finite JSON", kind="other", status_code=422)
        body = {key: args[key] for key in ("client_request_id", "witness", "parameter_id", "value")}
        try:
            data = self.post_json("/api/agent/shader-parameter", body, headers=headers)
            return self._shader_parameter_receipt(data, request_id, submit=True)
        except HextileClientError as exc:
            if (exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500
                    or exc.kind == "other" and exc.status_code is not None and 200 <= exc.status_code < 300):
                raise HextileClientError(
                    f"Shader parameter outcome unknown for client_request_id={request_id}; use status with this ID.",
                    kind="shader_parameter_outcome_unknown", receipt={"client_request_id": request_id}) from exc
            raise
        except Exception as exc:
            raise HextileClientError(
                f"Shader parameter outcome unknown for client_request_id={request_id}; use status with this ID.",
                kind="shader_parameter_outcome_unknown", receipt={"client_request_id": request_id}) from exc

    @staticmethod
    def _shader_parameter_receipt(data: Any, request_id: str, *, submit: bool) -> dict[str, Any]:
        if (not isinstance(data, Mapping) or (submit and data.get("ok") is not True)
                or "client_request_id" in data and data["client_request_id"] != request_id
                or type(data.get("ticket_id")) is not str
                or data.get("status") not in {"pending", "applied", "refused", "unknown"}):
            raise HextileClientError("Invalid Shader parameter receipt", kind="other", status_code=200)
        try:
            if str(uuid.UUID(data["ticket_id"])) != data["ticket_id"]:
                raise ValueError("noncanonical")
        except (ValueError, AttributeError):
            raise HextileClientError("Invalid Shader parameter receipt", kind="other", status_code=200) from None
        result = {"client_request_id": request_id, "ticket_id": data["ticket_id"], "status": data["status"]}
        for key in ("parameter_id", "reason"):
            if key in data:
                if type(data[key]) is not str or len(data[key]) > 128:
                    raise HextileClientError("Invalid Shader parameter receipt", kind="other", status_code=200)
                result[key] = data[key]
        return result

    def propose_shader(self, body: Mapping[str, Any]) -> Any:
        """POST /api/agent/shader-proposals. Does not prepare, consume, import, or delete."""
        validate_shader_proposal(body)
        return self.post_json(
            "/api/agent/shader-proposals",
            dict(body),
            headers={"X-Hextile-Agent": "mcp"},
        )

    @staticmethod
    def _shader_sequence_error(exc: HextileClientError, *, uncertain: bool = False) -> HextileClientError:
        code = None
        try:
            detail = json.loads(exc.body or "").get("detail")
            if isinstance(detail, Mapping) and type(detail.get("code")) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", detail["code"]):
                code = detail["code"]
        except (ValueError, AttributeError, TypeError):
            pass
        if uncertain and (exc.kind == "app_down" or exc.status_code is None
                          or exc.status_code >= 500
                          or exc.kind == "other" and exc.status_code is not None and 200 <= exc.status_code < 300):
            return HextileClientError(
                "Shader sequence POST outcome unknown. GET the preflight-known sequence_id and compare request_hash; never mint a new ID or blindly repost.",
                status_code=exc.status_code, kind="shader_sequence_outcome_unknown",
                receipt={"status": "unknown"})
        return HextileClientError("Shader sequence refused or unavailable", status_code=exc.status_code,
                                  kind=exc.kind, receipt={"code": code or "shader_sequence_refused"})

    @staticmethod
    def _shader_sequence_receipt(data: Any, *, preflight: bool) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise HextileClientError("Invalid Shader sequence receipt", kind="other")
        allowed = ("sequence_id", "status", "request_hash", "recipe_hash")
        result = {key: data[key] for key in allowed if key in data and type(data[key]) is str}
        if (re.fullmatch(r"seq_[0-9a-f]{32}", result.get("sequence_id", "")) is None
                or re.fullmatch(r"sha256:[0-9a-f]{64}", result.get("request_hash", "")) is None
                or result.get("status") not in (("ready", "existing") if preflight else
                                                ("queued", "processing", "completed", "completed_with_errors",
                                                 "failed", "cancelled", "incomplete", "paused", "stopped"))):
            raise HextileClientError("Invalid Shader sequence receipt", kind="other")
        if "recipe_hash" in result and re.fullmatch(r"sha256:[0-9a-f]{64}", result["recipe_hash"]) is None:
            raise HextileClientError("Invalid Shader sequence receipt", kind="other")
        return result

    def _shader_sequence_post(self, body: Mapping[str, Any], *, preflight: bool) -> dict[str, Any]:
        validate_shader_sequence_request(body)
        if body.get("publication_mode") != "deferred" or body.get("supersampling", 1) != 1:
            self._require_native_render()
        path = "/api/shaders/sequences/preflight" if preflight else "/api/shaders/sequences"
        try:
            data = self.post_json(path, dict(body),
                                  headers={"X-Hextile-Project-Witness": body["project_context_witness"]})
            return self._shader_sequence_receipt(data, preflight=preflight)
        except HextileClientError as exc:
            raise self._shader_sequence_error(exc, uncertain=not preflight) from exc
        except Exception as exc:  # Transport/read failures can include private exception text.
            safe = HextileClientError("Shader sequence transport failed", kind="other")
            raise self._shader_sequence_error(safe, uncertain=not preflight) from exc

    def preflight_shader_sequence(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._shader_sequence_post(body, preflight=True)

    def inspect_shader_sequence_output(self, args: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(args, Mapping) or set(args) != {"request"}:
            raise HextileClientError("Expected a closed Shader destination inspection", kind="other", status_code=422)
        request = args["request"]
        validate_shader_sequence_request(request)
        if request.get("folder_export") is None:
            raise HextileClientError("Inspection needs a selected Shader destination", kind="other", status_code=422)
        self._require_native_render()
        try:
            data = self.post_json("/api/shaders/sequences/inspect", {"request": dict(request)},
                                  headers={"X-Hextile-Project-Witness": request["project_context_witness"]},
                                  timeout=LONG_OPERATION_TIMEOUT_S)
            return _native_inspection_result(data, "shader")
        except HextileClientError as exc:
            raise self._shader_sequence_error(exc) from exc

    def render_shader_sequence(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._shader_sequence_post(body, preflight=False)

    def get_shader_sequence(self, sequence_id: str) -> dict[str, Any]:
        if type(sequence_id) is not str or re.fullmatch(r"seq_[0-9a-f]{32}", sequence_id) is None:
            raise HextileClientError("Expected a known Shader sequence ID", kind="other", status_code=422)
        try:
            data = self.get_json(f"/api/shaders/sequences/{sequence_id}")
        except HextileClientError as exc:
            if exc.status_code == 404:
                raise HextileClientError(
                    "Known Shader sequence ID is absent; an uncertain render POST remains outcome unknown. Do not blindly repost.",
                    status_code=404, kind="shader_sequence_outcome_unknown",
                    receipt={"sequence_id": sequence_id, "status": "unknown"}) from exc
            raise self._shader_sequence_error(exc) from exc
        except Exception as exc:  # Keep unexpected transport details out of MCP results.
            raise HextileClientError("Shader sequence status unavailable", kind="other") from exc
        if not isinstance(data, Mapping) or data.get("sequence_id") != sequence_id:
            raise HextileClientError("Invalid Shader sequence status", kind="other")
        result: dict[str, Any] = {"sequence_id": sequence_id}
        statuses = {"queued", "processing", "completed", "completed_with_errors", "failed",
                    "cancelled", "paused", "incomplete", "stopped"}
        if data.get("status") in statuses:
            result["status"] = data["status"]
        if data.get("publication_mode") == "deferred":
            result["publication_mode"] = "deferred"
        for key in ("request_hash", "recipe_hash", "render_identity"):
            if type(data.get(key)) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", data[key]):
                result[key] = data[key]
        if type(data.get("attempt_id")) is str and re.fullmatch(r"attempt_[0-9a-f]{32}", data["attempt_id"]):
            result["attempt_id"] = data["attempt_id"]
        elif data.get("attempt_id") is None and "attempt_id" in data:
            result["attempt_id"] = None
        for key in ("frame_count", "width", "height", "published_cursor", "frames_pending",
                    "frames_queued", "frames_processing", "frames_completed", "frames_failed", "attempt_revision"):
            if type(data.get(key)) is int and data[key] >= 0:
                result[key] = data[key]
        if data.get("current_frame_index") is None and "current_frame_index" in data:
            result["current_frame_index"] = None
        elif type(data.get("current_frame_index")) is int and data["current_frame_index"] >= 0:
            result["current_frame_index"] = data["current_frame_index"]
        rate = data.get("frame_rate")
        if isinstance(rate, Mapping) and all(type(rate.get(key)) is int and rate[key] > 0 for key in ("num", "den")):
            result["frame_rate"] = {key: rate[key] for key in ("num", "den")}
        for key in ("start_time", "end_time"):
            value = data.get(key)
            if isinstance(value, Mapping) and all(type(value.get(part)) is str and re.fullmatch(r"[0-9]{1,32}", value[part]) for part in ("num", "den")):
                result[key] = {part: value[part] for part in ("num", "den")}
        output = data.get("output")
        if isinstance(output, Mapping) and output.get("projection") in ("equirectangular", "fulldome", "fulldome_angular"):
            projected = {"projection": output["projection"]}
            for key in ("diameter", "fov_deg", "pan", "tilt", "roll"):
                value = output.get(key)
                if type(value) in (int, float) and math.isfinite(value):
                    projected[key] = value
            result["output"] = projected
        def attempt(source: Any) -> dict[str, Any] | None:
            if not isinstance(source, Mapping):
                return None
            projected: dict[str, Any] = {}
            for key in ("attempt_id", "transaction_fingerprint"):
                pattern = r"attempt_[0-9a-f]{32}" if key == "attempt_id" else r"sha256:[0-9a-f]{64}"
                if type(source.get(key)) is str and re.fullmatch(pattern, source[key]):
                    projected[key] = source[key]
            if source.get("status") in {"queued", "running", "interrupted", "completed", "failed", "cancelled"}:
                projected["status"] = source["status"]
            for key in ("attempt_revision", "frames_completed", "frames_failed", "quality_if_jpg"):
                if type(source.get(key)) is int and source[key] >= 0:
                    projected[key] = source[key]
            if source.get("format") in ("PNG", "JPG"):
                projected["format"] = source["format"]
            if type(source.get("destination_available")) is bool:
                projected["destination_available"] = source["destination_available"]
            observation = _native_observation(source.get("observation"))
            if observation is not None:
                projected["observation"] = observation
            return projected
        if "folder_export" in data:
            result["folder_export"] = attempt(data["folder_export"])
        if isinstance(data.get("publication_attempts"), list):
            result["publication_attempts"] = [attempt(item) for item in data["publication_attempts"][:8]
                                              if isinstance(item, Mapping)]
        result.update(_native_sequence_fields(data))
        return result

    @staticmethod
    def _shader_export_args(args: Mapping[str, Any], *, submit: bool) -> tuple[str, dict[str, Any]]:
        required = {"sequence_id", "destination_folder", "format"}
        optional = {"quality_if_jpg"}
        if submit:
            required.add("transaction_fingerprint")
        if (not isinstance(args, Mapping) or not required <= args.keys()
                or args.keys() - required - optional):
            raise HextileClientError("Expected closed Shader folder export intent", kind="other", status_code=422)
        sid = args["sequence_id"]
        folder = args["destination_folder"]
        encoding = args["format"]
        quality = args.get("quality_if_jpg")
        if (type(sid) is not str or re.fullmatch(r"seq_[0-9a-f]{32}", sid) is None
                or type(folder) is not str or not folder or "\x00" in folder
                or type(encoding) is not str or encoding not in ("PNG", "JPG")
                or (encoding == "JPG") != (type(quality) is int and 1 <= quality <= 100)
                or (encoding == "PNG" and "quality_if_jpg" in args)):
            raise HextileClientError("Invalid Shader folder export intent", kind="other", status_code=422)
        body = {"destination_folder": folder, "format": encoding,
                "quality_if_jpg": quality}
        if submit:
            fingerprint = args["transaction_fingerprint"]
            if type(fingerprint) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint) is None:
                raise HextileClientError("Invalid Shader export fingerprint", kind="other", status_code=422)
            body["transaction_fingerprint"] = fingerprint
        return sid, body

    @staticmethod
    def _shader_export_receipt(data: Any, sequence_id: str, *, preflight: bool) -> dict[str, Any]:
        if not isinstance(data, Mapping) or data.get("sequence_id") != sequence_id:
            raise HextileClientError("Invalid Shader export receipt", kind="other")
        result = {"sequence_id": sequence_id}
        patterns = {"attempt_id": r"attempt_[0-9a-f]{32}",
                    "transaction_fingerprint": r"sha256:[0-9a-f]{64}",
                    "recipe_hash": r"sha256:[0-9a-f]{64}"}
        for key, pattern in patterns.items():
            if type(data.get(key)) is str and re.fullmatch(pattern, data[key]):
                result[key] = data[key]
        if ("attempt_id" not in result or "transaction_fingerprint" not in result
                or result["attempt_id"] != "attempt_" + result["transaction_fingerprint"][7:39]):
            raise HextileClientError("Invalid Shader export receipt", kind="other")
        allowed_status = {"ready", "existing"} if preflight else {"queued", "existing"}
        if type(data.get("status")) is not str or data["status"] not in allowed_status:
            raise HextileClientError("Invalid Shader export receipt", kind="other", status_code=202)
        result["status"] = data["status"]
        if type(data.get("attempt_revision")) is int and data["attempt_revision"] >= 0:
            result["attempt_revision"] = data["attempt_revision"]
        return result

    def preflight_shader_sequence_export(self, args: Mapping[str, Any]) -> dict[str, Any]:
        sid, body = self._shader_export_args(args, submit=False)
        try:
            data = self.post_json(f"/api/shaders/sequences/{sid}/export/preflight", body)
            return self._shader_export_receipt(data, sid, preflight=True)
        except HextileClientError as exc:
            raise self._shader_sequence_error(exc) from exc
        except Exception as exc:
            raise HextileClientError("Shader export preflight unavailable", kind="other") from exc

    def export_shader_sequence(self, args: Mapping[str, Any]) -> dict[str, Any]:
        sid, body = self._shader_export_args(args, submit=True)
        try:
            data = self.post_json(f"/api/shaders/sequences/{sid}/export", body)
            receipt = self._shader_export_receipt(data, sid, preflight=False)
            if receipt["transaction_fingerprint"] != body["transaction_fingerprint"]:
                raise HextileClientError("Invalid Shader export acknowledgement", kind="other", status_code=202)
            return receipt
        except HextileClientError as exc:
            if (exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500
                    or exc.kind == "other" and exc.status_code is not None and 200 <= exc.status_code < 300):
                raise HextileClientError(
                    "Shader export POST outcome unknown. GET the preflight-known sequence_id and compare "
                    "attempt_id and transaction_fingerprint; never blindly repost.",
                    status_code=exc.status_code, kind="shader_sequence_outcome_unknown",
                    receipt={"status": "unknown"}) from exc
            raise self._shader_sequence_error(exc) from exc
        except Exception as exc:
            raise HextileClientError(
                "Shader export POST outcome unknown. GET the preflight-known sequence_id and compare "
                "attempt_id and transaction_fingerprint; never blindly repost.",
                kind="shader_sequence_outcome_unknown", receipt={"status": "unknown"}) from exc

    def control_shader_sequence(self, args: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(args, Mapping) or not {"sequence_id", "action"} <= set(args):
            raise HextileClientError("Expected closed Shader sequence control", kind="other", status_code=422)
        sid, action = args["sequence_id"], args["action"]
        if type(sid) is not str or re.fullmatch(r"seq_[0-9a-f]{32}", sid) is None or type(action) is not str:
            raise HextileClientError("Invalid Shader sequence control target", kind="other", status_code=422)
        headers = None
        if action == "stop" and set(args) == {"sequence_id", "action", "run_id"}:
            if type(args["run_id"]) is not str or re.fullmatch(r"[0-9a-f]{32}", args["run_id"]) is None:
                raise HextileClientError("Stop requires the observed native run_id", kind="other", status_code=422)
            suffix, body = "stop", {"run_id": args["run_id"]}
        elif action == "resume" and set(args) == {"sequence_id", "action"}:
            suffix, body = "resume", None
        elif action == "continue" and set(args) == {"sequence_id", "action", "request", "inspection_fingerprint"}:
            request = args["request"]
            validate_shader_sequence_request(request)
            if (request.get("folder_export") is None or type(args["inspection_fingerprint"]) is not str
                    or _WORKSPACE_DIGEST.fullmatch(args["inspection_fingerprint"]) is None):
                raise HextileClientError("Continue requires the inspected Shader destination", kind="other", status_code=422)
            self._require_native_render()
            suffix, body = "continue", {"request": dict(request), "inspection_fingerprint": args["inspection_fingerprint"]}
            headers = {"X-Hextile-Project-Witness": request["project_context_witness"]}
        elif action in {"cancel_export", "retry_export"} and set(args) == {"sequence_id", "action", "attempt_id"}:
            attempt = args["attempt_id"]
            if type(attempt) is not str or re.fullmatch(r"attempt_[0-9a-f]{32}", attempt) is None:
                raise HextileClientError("Invalid Shader export attempt", kind="other", status_code=422)
            suffix, body = {"cancel_export": "export/cancel", "retry_export": "export/retry"}[action], {"attempt_id": attempt}
        else:
            raise HextileClientError("Invalid closed Shader sequence control", kind="other", status_code=422)
        try:
            data = self.post_json(f"/api/shaders/sequences/{sid}/{suffix}", body, headers=headers,
                                  timeout=LONG_OPERATION_TIMEOUT_S if action == "continue" else None)
            if not isinstance(data, Mapping) or data.get("sequence_id") != sid:
                raise HextileClientError("Invalid Shader sequence control acknowledgement", kind="other", status_code=202)
            statuses = {"queued", "processing", "completed", "completed_with_errors", "failed",
                        "cancelled", "paused", "incomplete", "stopped"} if action not in {"cancel_export", "retry_export"} else {
                        "queued", "running", "completed", "failed", "cancelled", "interrupted"}
            if type(data.get("status")) is not str or data["status"] not in statuses:
                raise HextileClientError("Invalid Shader sequence control acknowledgement", kind="other", status_code=202)
            if action in {"cancel_export", "retry_export"}:
                folder = data.get("folder_export")
                if (not isinstance(folder, Mapping) or folder.get("attempt_id") != args["attempt_id"]
                        or folder.get("status") != data["status"]):
                    raise HextileClientError("Invalid Shader export control acknowledgement", kind="other", status_code=202)
            result = {"sequence_id": sid, "action": action, "status": data["status"]}
            if action in {"cancel_export", "retry_export"}:
                result["attempt_id"] = args["attempt_id"]
            if action == "stop":
                result["run_id"] = args["run_id"]
            if action == "continue":
                run_id = data.get("run_id")
                if run_id is not None and (type(run_id) is not str or re.fullmatch(r"[0-9a-f]{32}", run_id) is None):
                    raise HextileClientError("Invalid Shader Continue run receipt", kind="other", status_code=202)
                result["run_id"] = run_id
            return result
        except HextileClientError as exc:
            if (exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500
                    or exc.kind == "other" and 200 <= exc.status_code < 300):
                raise HextileClientError(
                    "Shader control POST outcome unknown. GET the known sequence_id and original run/attempt/inspection receipt before another action.",
                    status_code=exc.status_code, kind="shader_sequence_outcome_unknown",
                    receipt={"status": "unknown", "sequence_id": sid,
                             **({"inspection_fingerprint": args["inspection_fingerprint"],
                                 "idempotency_key": args["request"]["idempotency_key"]} if action == "continue" else {})}) from exc
            if exc.status_code == 409 and self._fractal_code(exc) == "sequence_run_changed":
                raise HextileClientError("Native Shader run changed. GET fresh status; never retry Stop without its observed run_id.",
                                         status_code=409, kind="http", receipt={"sequence_id": sid, "code": "sequence_run_changed"}) from exc
            raise self._shader_sequence_error(exc) from exc
        except Exception as exc:
            raise HextileClientError(
                "Shader control POST outcome unknown. GET the known sequence_id and original intent before another action.",
                kind="shader_sequence_outcome_unknown", receipt={"status": "unknown", "sequence_id": sid}) from exc

    @staticmethod
    def _shader_timeline_receipt(data: Any, request_id: str, *, submit: bool) -> dict[str, Any]:
        reasons = {"stale_snapshot", "wrong_owner", "mcp_disabled", "expired", "studio_closed",
                   "cancelled", "preview_unavailable", "outcome_unconfirmed"}
        if (not isinstance(data, Mapping) or (submit and data.get("ok") is not True)
                or "client_request_id" in data and data["client_request_id"] != request_id
                or type(data.get("ticket_id")) is not str):
            raise HextileClientError("Invalid Shader timeline receipt", kind="other", status_code=200)
        try:
            if str(uuid.UUID(data["ticket_id"])) != data["ticket_id"]:
                raise ValueError("noncanonical")
        except (ValueError, AttributeError):
            raise HextileClientError("Invalid Shader timeline receipt", kind="other", status_code=200) from None
        status = data.get("status")
        if type(status) is not str or status not in {"pending", "applied", "refused", "unknown"}:
            raise HextileClientError("Invalid Shader timeline receipt", kind="other", status_code=200)
        result = {"client_request_id": request_id, "ticket_id": data["ticket_id"], "status": status}
        if "action" in data:
            if type(data["action"]) is not str or data["action"] not in {"play", "pause", "seek", "reset"}:
                raise HextileClientError("Invalid Shader timeline receipt", kind="other", status_code=200)
            result["action"] = data["action"]
        if "reason" in data:
            if type(data["reason"]) is not str or data["reason"] not in reasons:
                raise HextileClientError("Invalid Shader timeline receipt", kind="other", status_code=200)
            result["reason"] = data["reason"]
        return result

    @staticmethod
    def _shader_timeline_error(exc: HextileClientError) -> HextileClientError:
        code = None
        try:
            detail = json.loads(exc.body or "").get("detail")
            if type(detail) is str and detail in {"invalid_external_authority", "request_conflict",
                                                      "mcp_disabled", "stale_snapshot", "apply_busy",
                                                      "invalid_client_request_id"}:
                code = detail
        except (ValueError, AttributeError, TypeError):
            pass
        return HextileClientError("Shader timeline refused or unavailable", kind=exc.kind,
                                  status_code=exc.status_code, receipt={"code": code} if code else None)

    def control_shader_timeline(self, args: Mapping[str, Any]) -> Any:
        """Submit once or recover the caller's known request ID; never poll the UI delivery door."""
        request_id = args.get("client_request_id") if isinstance(args, Mapping) else None
        if type(request_id) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id) is None:
            raise HextileClientError("Invalid Shader timeline client_request_id", kind="other", status_code=422)
        operation = args.get("operation")
        if operation == "status":
            if set(args) != {"operation", "client_request_id"}:
                raise HextileClientError("Expected exact timeline status arguments", kind="other", status_code=422)
            try:
                data = self.get_json(f"/api/agent/shader-timeline-control/requests/{request_id}",
                                     headers={"X-Hextile-Agent": "mcp"})
                return self._shader_timeline_receipt(data, request_id, submit=False)
            except HextileClientError as exc:
                if exc.status_code == 404:
                    raise HextileClientError(
                        f"Shader timeline outcome unknown for client_request_id={request_id}; expiry or absence is not refusal.",
                        kind="shader_timeline_outcome_unknown", status_code=404,
                        receipt={"client_request_id": request_id, "status": "unknown"}) from exc
                raise self._shader_timeline_error(exc) from exc
            except Exception as exc:
                raise HextileClientError("Shader timeline status unavailable", kind="other") from exc
        if operation != "submit" or not {"operation", "client_request_id", "action", "witness"} <= set(args):
            raise HextileClientError("Expected exact timeline submit arguments", kind="other", status_code=422)
        action = args["action"]
        expected = {"operation", "client_request_id", "action", "witness"} | ({"time_seconds"} if action == "seek" else set())
        if set(args) != expected or action not in {"play", "pause", "seek", "reset"}:
            raise HextileClientError("Invalid Shader timeline action", kind="other", status_code=422)
        if action == "seek" and (type(args["time_seconds"]) not in (int, float)
                                 or not math.isfinite(args["time_seconds"])
                                 or not 0 <= args["time_seconds"] <= 86400):
            raise HextileClientError("Invalid Shader timeline seek time", kind="other", status_code=422)
        witness = args["witness"]
        witness_keys = {"studio_surface_id", "project_context_witness", "shader", "base",
                        "owner_id", "owner_generation", "viewer_generation", "source_epoch"}
        if (type(witness) is not dict or set(witness) != witness_keys
                or any(type(witness[key]) is not str or not witness[key]
                       for key in ("studio_surface_id", "project_context_witness", "owner_id"))
                or any(type(witness[key]) is not int or witness[key] < 0
                       for key in ("owner_generation", "viewer_generation", "source_epoch"))
                or type(witness["shader"]) is not dict or set(witness["shader"]) != {"origin", "shaderId"}
                or witness["shader"]["origin"] not in {"builtin", "user", "project"}
                or type(witness["shader"]["shaderId"]) is not str
                or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", witness["shader"]["shaderId"]) is None
                or type(witness["base"]) is not dict):
            raise HextileClientError("Invalid Shader timeline witness", kind="other", status_code=422)
        body = {key: value for key, value in args.items() if key != "operation"}
        try:
            receipt = self.post_json("/api/agent/shader-timeline-control", body,
                                     headers={"X-Hextile-Agent": "mcp"})
        except http.client.HTTPException as exc:
            raise HextileClientError(
                f"Shader timeline outcome unknown for client_request_id={request_id}; use status with this ID.",
                kind="shader_timeline_outcome_unknown", receipt={"client_request_id": request_id}) from exc
        except HextileClientError as exc:
            if (exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500
                    or exc.kind == "other" and exc.status_code is not None
                    and 200 <= exc.status_code < 300):
                raise HextileClientError(
                    f"Shader timeline outcome unknown for client_request_id={request_id}; use status with this ID.",
                    kind="shader_timeline_outcome_unknown", receipt={"client_request_id": request_id}) from exc
            raise self._shader_timeline_error(exc) from exc
        except Exception as exc:
            raise HextileClientError(
                f"Shader timeline outcome unknown for client_request_id={request_id}; use status with this ID.",
                kind="shader_timeline_outcome_unknown", receipt={"client_request_id": request_id}) from exc
        try:
            return self._shader_timeline_receipt(receipt, request_id, submit=True)
        except HextileClientError as exc:
            raise HextileClientError(
                f"Shader timeline acknowledgement unknown for client_request_id={request_id}; use status with this ID.",
                kind="shader_timeline_outcome_unknown", receipt={"client_request_id": request_id}) from exc

    def request_shader_doctor(self, args: Mapping[str, Any]) -> Any:
        """Submit once; an uncertain outcome is reconciled only by exact-ID GET."""
        validate_shader_doctor("request", args)
        request_id = args["request_id"]
        try:
            receipt = self.request_json(
                "POST", "/api/agent/shader-doctor/requests", dict(args),
                headers={"X-Hextile-Agent": "mcp"},
            )
        except http.client.HTTPException as exc:
            raise HextileClientError(
                f"Shader Doctor outcome unknown for request_id={request_id}; poll get_shader_doctor with this ID. Do not resubmit automatically.",
                kind="shader_doctor_outcome_unknown", receipt={"request_id": request_id},
            ) from exc
        except HextileClientError as exc:
            if exc.kind == "app_down" or (exc.kind == "other" and exc.status_code is not None
                                          and 200 <= exc.status_code < 300):
                raise HextileClientError(
                    f"Shader Doctor outcome unknown for request_id={request_id}; poll get_shader_doctor with this ID. Do not resubmit automatically.",
                    kind="shader_doctor_outcome_unknown", receipt={"request_id": request_id},
                ) from exc
            raise
        if not isinstance(receipt, dict) or receipt.get("request_id") != request_id:
            raise HextileClientError(
                f"Shader Doctor acknowledgement unknown for request_id={request_id}; poll get_shader_doctor with this ID.",
                kind="shader_doctor_outcome_unknown", receipt={"request_id": request_id},
            )
        return receipt

    def get_shader_doctor(self, args: Mapping[str, Any]) -> Any:
        """Read the exact request receipt; this never starts another GPU pass."""
        validate_shader_doctor("get", args)
        return self.get_json(
            f"/api/agent/shader-doctor/requests/{args['request_id']}",
            params={"project_context_witness": args["project_context_witness"]},
            headers={"X-Hextile-Agent": "mcp"},
        )

    def get_shader_asset_state(self, args: Mapping[str, Any]) -> Any:
        _native_shader_args("state", args)
        return _native_read_result(self.request_json("GET", "/api/shaders/agent-operations/asset-state", params={
            "origin": args["shader"]["origin"], "shader_id": args["shader"]["shaderId"],
            "project_context_witness": args["project_context_witness"]}), kind="state")

    def list_shader_assets(self, args: Mapping[str, Any]) -> dict:
        _native_read_args(args, {"project_context_witness"}, {"shelf", "search", "cursor", "limit"})
        return _native_read_result(self.request_json("GET", "/api/shaders/agent-operations/assets",
                                                     params=dict(args)), kind="assets", entries=50)

    def get_shader_history(self, args: Mapping[str, Any]) -> dict:
        _native_read_args(args, {"shader", "project_context_witness"}, {"kind", "cursor", "limit"})
        params = {"origin": args["shader"]["origin"], "shader_id": args["shader"]["shaderId"],
                  "project_context_witness": args["project_context_witness"]}
        params.update({key: args[key] for key in ("kind", "cursor", "limit") if key in args})
        return _native_read_result(self.request_json("GET", "/api/shaders/agent-operations/history",
                                                     params=params), kind="history", entries=20)

    def get_shader_looks(self, args: Mapping[str, Any]) -> dict:
        _native_read_args(args, {"shader", "project_context_witness"})
        return _native_read_result(self.request_json("GET", "/api/shaders/agent-operations/looks", params={
            "origin": args["shader"]["origin"], "shader_id": args["shader"]["shaderId"],
            "project_context_witness": args["project_context_witness"]}), kind="looks", entries=128)

    def _shader_history_write(self, args: Mapping[str, Any], operation: str, path: str) -> dict:
        checked = dict(args)
        if operation.startswith("shader_checkpoint_"):
            if checked.pop("action", None) != operation.removeprefix("shader_checkpoint_"):
                raise HextileClientError("Invalid checkpoint action", status_code=422, kind="other")
        elif operation.startswith("shader_history_"):
            if checked.pop("action", None) != operation.removeprefix("shader_history_"):
                raise HextileClientError("Invalid retention action", status_code=422, kind="other")
        _native_history_args(operation, checked)
        try:
            receipt = self.request_json("POST", path, dict(args))
        except HextileClientError as exc:
            if exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError("Shader history outcome unknown; read shader_get_operation by original request_id. Do not submit again.",
                    kind="shader_operation_outcome_unknown", receipt={"request_id": checked["request_id"]}) from exc
            raise
        if (not isinstance(receipt, dict) or receipt.get("request_id") != checked["request_id"]
                or receipt.get("operation") != operation
                or receipt.get("state") not in {"pending", "applied", "saved", "refused", "failed", "unknown", "expired"}):
            raise HextileClientError("Shader history acknowledgement unknown; read shader_get_operation by original request_id.",
                kind="shader_operation_outcome_unknown", receipt={"request_id": checked["request_id"]})
        if len(json.dumps(receipt, ensure_ascii=False).encode("utf-8")) > 32768:
            raise HextileClientError("Shader history receipt exceeds result limit", kind="other")
        return receipt

    def save_shader_look(self, args: Mapping[str, Any]) -> dict:
        return self._shader_history_write(args, "shader_save_look", "/api/shaders/agent-operations/looks/save")

    def apply_shader_look(self, args: Mapping[str, Any]) -> dict:
        return self._shader_history_write(args, "shader_apply_look", "/api/shaders/agent-operations/looks/apply")

    def rename_shader_look(self, args: Mapping[str, Any]) -> dict:
        return self._shader_history_write(args, "shader_rename_look", "/api/shaders/agent-operations/looks/rename")

    def delete_shader_look(self, args: Mapping[str, Any]) -> dict:
        return self._shader_history_write(args, "shader_delete_look", "/api/shaders/agent-operations/looks/delete")

    def shader_checkpoint(self, args: Mapping[str, Any]) -> dict:
        action = args.get("action")
        if action not in {"save", "rename", "remove"}:
            raise HextileClientError("Invalid checkpoint action", status_code=422, kind="other")
        return self._shader_history_write(args, "shader_checkpoint_" + action,
                                          "/api/shaders/agent-operations/checkpoint")

    def restore_shader_revision(self, args: Mapping[str, Any]) -> dict:
        return self._shader_history_write(args, "shader_restore_revision", "/api/shaders/agent-operations/revisions/restore")

    def copy_shader_revision(self, args: Mapping[str, Any]) -> dict:
        return self._shader_history_write(args, "shader_copy_revision", "/api/shaders/agent-operations/revisions/copy")

    def shader_history_retention(self, args: Mapping[str, Any]) -> dict:
        action = args.get("action")
        if action not in {"preview", "compact", "uncompact"}:
            raise HextileClientError("Permanent history purge is a human action", status_code=403, kind="other")
        if action == "preview":
            checked = {key: value for key, value in args.items() if key != "action"}
            _native_history_args("shader_history_preview", checked)
            result = self.request_json("POST", "/api/shaders/agent-operations/history-retention", dict(args))
            if (not isinstance(result, dict) or not isinstance(result.get("preview_token"), str)
                    or len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 32768):
                raise HextileClientError("Invalid Shader history preview", kind="other")
            return result
        return self._shader_history_write(args, "shader_history_" + action,
                                          "/api/shaders/agent-operations/history-retention")

    def get_shader_project_conventions(self, args: Mapping[str, Any]) -> dict:
        _native_read_args(args, {"project_context_witness"})
        return _native_read_result(self.request_json("GET", "/api/shaders/agent-operations/project-conventions",
                                                     params=dict(args)), kind="conventions")

    def stage_shader_resource(self, args: Mapping[str, Any]) -> dict:
        required = {"shader", "project_context_witness", "base", "expected_working_digest", "source"}
        optional = {"resolution", "reduced_copy", "projection", "filter", "edge_u", "edge_v"}
        _native_read_args(args, required, optional)
        source = args["source"]
        fields = {"render_node": {"render_id", "node_id", "artifact_witness"},
                  "sequence_range": {"sequence_id", "start_index", "end_index", "fps_num", "fps_den"},
                  "local_path": set()}
        if (not isinstance(source, Mapping) or source.get("kind") not in fields
                or fields[source["kind"]] - source.keys()
                or set(source) - fields[source["kind"]] - {"kind"}
                - ({"path", "paths", "fps_num", "fps_den"} if source["kind"] == "local_path" else set())):
            raise HextileClientError("Invalid closed Shader resource source", status_code=422, kind="other")
        if source["kind"] == "local_path":
            paths = [source["path"]] if "path" in source else source.get("paths")
            if (("path" in source) == ("paths" in source) or type(paths) is not list or not 1 <= len(paths) <= 1024
                    or any(not _absolute_task_path(path) for path in paths)
                    or any(type(source[k]) is not int or source[k] < 1 for k in ("fps_num", "fps_den") if k in source)):
                raise HextileClientError("Expected absolute local task paths and positive FPS", status_code=422, kind="other")
        if (source["kind"] == "sequence_range" and
                (type(source["start_index"]) is not int or type(source["end_index"]) is not int
                 or source["end_index"] < source["start_index"])):
            raise HextileClientError("Invalid complete sequence range", status_code=422, kind="other")
        if args.get("resolution", "full") not in {"full", "4k", "8k", "12k", "16k"} or type(args.get("reduced_copy", False)) is not bool:
            raise HextileClientError("Invalid resource resolution", status_code=422, kind="other")
        result = self.request_json("POST", "/api/shaders/agent-operations/resources/stage", dict(args))
        if (type(result) is not dict or result.get("schema") != 1
                or type(result.get("frames")) is not list or not 1 <= len(result["frames"]) <= 1024
                or result.get("frame_count") != len(result["frames"])
                or any(type(row) is not dict or set(row) != {"index", "sha256", "width", "height"}
                       or type(row["index"]) is not int or type(row["sha256"]) is not str
                       or _WORKSPACE_DIGEST.fullmatch(row["sha256"]) is None for row in result["frames"])
                or len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 262144):
            raise HextileClientError("Shader resource stage acknowledgement is invalid", kind="other")
        return result

    def _shader_scoped_write(self, args: Mapping[str, Any], operation: str, path: str,
                             required: set[str], optional: set[str] = frozenset()) -> dict:
        if not isinstance(args, Mapping) or required - args.keys() or set(args) - required - optional:
            raise HextileClientError("Invalid closed Shader operation", status_code=422, kind="other")
        try:
            valid = type(args["request_id"]) is str and str(uuid.UUID(args["request_id"])) == args["request_id"] and uuid.UUID(args["request_id"]).version == 4
        except (ValueError, TypeError, KeyError):
            valid = False
        if not valid:
            raise HextileClientError("Invalid Shader request ID", status_code=422, kind="other")
        _native_read_args({key: args[key] for key in ("shader", "project_context_witness")}
                          if "shader" in required else {"project_context_witness": args["project_context_witness"]},
                          {"shader", "project_context_witness"} if "shader" in required else {"project_context_witness"})
        try:
            receipt = self.request_json("POST", path, dict(args))
        except HextileClientError as exc:
            if exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError("Shader operation outcome unknown; retry only the original request ID.",
                    kind="shader_operation_outcome_unknown", receipt={"request_id": args["request_id"]}) from exc
            raise
        if (type(receipt) is not dict or receipt.get("schema") != 1
                or receipt.get("request_id") != args["request_id"] or receipt.get("operation") != operation
                or receipt.get("state") not in {"pending", "applied", "saved", "refused", "failed", "unknown", "expired"}
                or len(json.dumps(receipt, ensure_ascii=False).encode("utf-8")) > 65536):
            raise HextileClientError("Shader operation acknowledgement unknown; use original request ID.",
                kind="shader_operation_outcome_unknown", receipt={"request_id": args["request_id"]})
        return receipt

    def set_shader_resource(self, args: Mapping[str, Any]) -> dict:
        required = {"shader", "project_context_witness", "request_id", "base", "expected_working_digest", "action", "slot_id"}
        optional = {"staged_token", "filter", "edge_u", "edge_v", "time_mode", "end_mode", "hold_index",
                    "library_intent", "confirmation_scope", "studio_surface_id", "expected_edit_sequence"}
        if args.get("action") not in {"attach", "replace", "locate", "remove", "settings"}:
            raise HextileClientError("Unknown resource action", status_code=422, kind="other")
        if (args["action"] in {"attach", "replace", "locate"}) != ("staged_token" in args):
            raise HextileClientError("Resource stage token mismatch", status_code=422, kind="other")
        return self._shader_scoped_write(args, "shader_set_resource", "/api/shaders/agent-operations/resources/set",
                                         required, optional)

    def get_shader_library_organization(self, args: Mapping[str, Any]) -> dict:
        required, optional = {"project_context_witness", "origin"}, {"cursor", "limit", "revision", "folder_id"}
        _native_read_args(args, required, optional)
        if args["origin"] not in {"project", "user"} or ("folder_id" in args and "revision" not in args):
            raise HextileClientError("Invalid organization scope", status_code=422, kind="other")
        result = self.request_json("GET", "/api/shaders/agent-operations/library/organization", params=dict(args))
        if (type(result) is not dict or set(result) != {"schema", "project_context_witness", "origin", "status",
                "revision", "folders", "assigned_shader_ids", "next_cursor"}
                or result["schema"] != 1 or result["origin"] != args["origin"]
                or result["project_context_witness"] != args["project_context_witness"]
                or result["status"] not in {"ready", "unavailable"}
                or type(result["folders"]) is not list or len(result["folders"]) > 50
                or type(result["assigned_shader_ids"]) is not list or len(result["assigned_shader_ids"]) > 50
                or len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 65536):
            raise HextileClientError("Invalid bounded organization read", kind="other")
        return result

    def organize_shader_library(self, args: Mapping[str, Any]) -> dict:
        required = {"request_id", "project_context_witness", "origin", "library_session_id", "expected_revision", "command"}
        if args.get("origin") not in {"project", "user"} or not isinstance(args.get("command"), Mapping):
            raise HextileClientError("Invalid organization action", status_code=422, kind="other")
        if args["command"].get("kind") not in {"createFolder", "renameFolder", "removeFolder", "moveShader", "moveShaders", "undo"}:
            raise HextileClientError("Unknown organization action", status_code=422, kind="other")
        return self._shader_scoped_write(args, "shader_organize_library", "/api/shaders/agent-operations/library/organize",
                                         required)

    def set_shader_tags(self, args: Mapping[str, Any]) -> dict:
        required = {"request_id", "project_context_witness", "command"}
        command = args.get("command")
        if (not isinstance(command, Mapping) or set(command) != {"kind", "shader", "tagId", "assigned"}
                or command.get("kind") != "setShaderTag" or type(command.get("assigned")) is not bool):
            raise HextileClientError("Invalid Shader tag assignment", status_code=422, kind="other")
        _native_shader_args("state", {"shader": command["shader"], "project_context_witness": args["project_context_witness"]})
        return self._shader_scoped_write(args, "shader_set_tags", "/api/shaders/agent-operations/library/tags", required)

    def set_shader_project_conventions(self, args: Mapping[str, Any]) -> dict:
        required = {"request_id", "project_context_witness", "expected_digest", "profiles", "default_profile_id"}
        if (type(args.get("profiles")) is not list or len(args["profiles"]) > 8
                or any(type(row) is not dict for row in args["profiles"])
                or (args.get("expected_digest") is not None and
                    (type(args["expected_digest"]) is not str or re.fullmatch(r"[0-9a-f]{64}", args["expected_digest"]) is None))):
            raise HextileClientError("Invalid Project convention CAS", status_code=422, kind="other")
        return self._shader_scoped_write(args, "shader_set_project_conventions",
            "/api/shaders/agent-operations/project-conventions", required)

    def rename_shader_asset(self, args: Mapping[str, Any]) -> Any:
        _native_shader_args("rename", args)
        request_id = args["request_id"]
        try:
            receipt = self.request_json("POST", "/api/shaders/agent-operations/rename", dict(args))
        except HextileClientError as exc:
            if exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError(
                    "Shader rename outcome unknown; read shader_get_operation by request_id. Do not submit again.",
                    kind="shader_operation_outcome_unknown", receipt={"request_id": request_id}) from exc
            raise
        if not isinstance(receipt, dict) or receipt.get("request_id") != request_id:
            raise HextileClientError(
                "Shader rename acknowledgement unknown; read shader_get_operation by request_id.",
                kind="shader_operation_outcome_unknown", receipt={"request_id": request_id})
        return receipt

    def delete_shader_asset(self, args: Mapping[str, Any]) -> Any:
        _native_shader_args("delete", args)
        request_id = args["request_id"]
        try:
            receipt = self.request_json("POST", "/api/shaders/agent-operations/delete", dict(args))
        except HextileClientError as exc:
            if exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError("Shader delete outcome unknown; read shader_get_operation by request_id.",
                    kind="shader_operation_outcome_unknown", receipt={"request_id": request_id}) from exc
            raise
        if not isinstance(receipt, dict) or receipt.get("request_id") != request_id:
            raise HextileClientError("Shader delete acknowledgement unknown; read shader_get_operation by request_id.",
                kind="shader_operation_outcome_unknown", receipt={"request_id": request_id})
        return receipt

    def _mounted_shader_action(self, args: Mapping[str, Any], operation: str, path: str) -> dict:
        common = {"shader", "project_context_witness", "studio_surface_id", "request_id", "expected_edit_sequence"}
        extras = ({"action", "seed", "capture_defaults"} if operation == "shader_set_capture" else
                  {"action", "bpm", "speed"} if operation == "shader_control_clock" else
                  {"target"} if operation == "shader_open_asset" else
                  set() if operation == "shader_save_asset" else
                  {"title"} if operation == "shader_save_as" else
                  {"direction", "owner"})
        if not isinstance(args, Mapping) or not common <= set(args) or set(args) - common - extras:
            raise HextileClientError("Invalid mounted Shader action", kind="other", status_code=422)
        ref = args["shader"]
        try:
            valid_id = str(uuid.UUID(args["request_id"])) == args["request_id"] and uuid.UUID(args["request_id"]).version == 4
        except (ValueError, AttributeError, TypeError):
            valid_id = False
        if (not valid_id or type(ref) is not dict or set(ref) != {"origin", "shaderId"}
                or ref["origin"] not in {"builtin", "user", "project"}
                or type(ref["shaderId"]) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", ref["shaderId"])
                or any(type(args[key]) is not str or not 1 <= len(args[key]) <= 256
                       for key in ("project_context_witness", "studio_surface_id"))
                or type(args["expected_edit_sequence"]) is not int or not 0 <= args["expected_edit_sequence"] <= 2**53 - 1):
            raise HextileClientError("Invalid mounted Shader owner", kind="other", status_code=422)
        if operation == "shader_set_capture":
            if args.get("action") == "live_seed":
                valid = (set(args) == common | {"action", "seed"} and type(args["seed"]) is int
                         and 0 <= args["seed"] <= 0xffffffff)
            else:
                valid = (args.get("action") == "defaults" and set(args) == common | {"action", "capture_defaults"}
                         and type(args["capture_defaults"]) is dict
                         and set(args["capture_defaults"]) == {"frame", "time", "time_delta", "frame_rate",
                                                                "pointer", "seed", "ray_origin"})
        elif operation == "shader_control_clock":
            action = args.get("action")
            valid = action in {"tap", "align", "reset_master", "reanchor"}
            if action == "reanchor":
                valid = valid and bool({"bpm", "speed"} & set(args))
                valid = valid and all(type(args[key]) in {int, float} and math.isfinite(args[key])
                                      and (0 < args[key] <= 1000 if key == "bpm" else 0 <= args[key] <= 1024)
                                      for key in ("bpm", "speed") if key in args)
            else:
                valid = valid and set(args) == common | {"action"}
        elif operation == "shader_open_asset":
            target = args.get("target")
            valid = (set(args) == common | {"target"} and type(target) is dict
                     and set(target) == {"origin", "shaderId"}
                     and target["origin"] in {"builtin", "user", "project"}
                     and type(target["shaderId"]) is str
                     and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", target["shaderId"]) is not None
                     and target != ref)
        elif operation == "shader_save_asset":
            valid = set(args) == common and ref["origin"] in {"user", "project"}
        elif operation == "shader_save_as":
            valid = (set(args) in (common, common | {"title"})
                     and ("title" not in args or type(args["title"]) is str
                          and 1 <= len(args["title"]) <= 256))
        else:
            owner = args.get("owner")
            valid = (set(args) == common | {"direction", "owner"} and type(args["direction"]) is int
                     and args["direction"] in {-1, 1} and type(owner) is dict
                     and set(owner) == {"owner_id", "owner_generation", "viewer_generation", "source_epoch"}
                     and type(owner["owner_id"]) is str and 1 <= len(owner["owner_id"]) <= 128
                     and all(type(owner[key]) is int and owner[key] >= 0
                             for key in ("owner_generation", "viewer_generation", "source_epoch")))
        try:
            bounded = len(json.dumps(dict(args), allow_nan=False).encode("utf-8")) <= 4096
        except (TypeError, ValueError, UnicodeError):
            bounded = False
        if not valid or not bounded:
            raise HextileClientError("Invalid mounted Shader action", kind="other", status_code=422)
        try:
            receipt = self.request_json("POST", path, dict(args))
        except HextileClientError as exc:
            if exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError(
                    "Mounted Shader outcome unknown; read shader_get_operation with the original request_id.",
                    kind="shader_operation_outcome_unknown", receipt={"request_id": args["request_id"]}) from exc
            raise
        if (type(receipt) is not dict or receipt.get("request_id") != args["request_id"]
                or receipt.get("operation") != operation
                or receipt.get("state") not in {"pending", "applied", "refused", "unknown", "expired"}):
            raise HextileClientError("Mounted Shader acknowledgement unknown; read shader_get_operation.",
                                     kind="shader_operation_outcome_unknown", receipt={"request_id": args["request_id"]})
        return receipt

    def set_shader_capture(self, args: Mapping[str, Any]) -> dict:
        return self._mounted_shader_action(args, "shader_set_capture", "/api/shaders/agent-operations/capture")

    def control_shader_clock(self, args: Mapping[str, Any]) -> dict:
        return self._mounted_shader_action(args, "shader_control_clock", "/api/shaders/agent-operations/clock")

    def step_shader_frame(self, args: Mapping[str, Any]) -> dict:
        return self._mounted_shader_action(args, "shader_step_frame", "/api/shaders/agent-operations/frame-step")

    def open_shader_asset(self, args: Mapping[str, Any]) -> dict:
        return self._mounted_shader_action(args, "shader_open_asset", "/api/shaders/agent-operations/open")

    def save_shader_asset(self, args: Mapping[str, Any]) -> dict:
        return self._mounted_shader_action(args, "shader_save_asset", "/api/shaders/agent-operations/save")

    def save_shader_as(self, args: Mapping[str, Any]) -> dict:
        return self._mounted_shader_action(args, "shader_save_as", "/api/shaders/agent-operations/save-as")

    def _create_shader_asset(self, args: Mapping[str, Any], action: str) -> dict:
        if not isinstance(args, Mapping):
            raise HextileClientError("Invalid Shader creation", kind="other", status_code=422)
        source = ({"origin": "builtin", "shaderId": "hx_starter"} if action == "new" else
                  None if action == "paste" else args.get("shader"))
        if action == "paste":
            try:
                valid_id = (type(args.get("request_id")) is str
                            and str(uuid.UUID(args["request_id"])) == args["request_id"]
                            and uuid.UUID(args["request_id"]).version == 4)
            except (ValueError, AttributeError):
                valid_id = False
            if (not valid_id or type(args.get("project_context_witness")) is not str
                    or not args["project_context_witness"]):
                raise HextileClientError("Invalid Shader creation", kind="other", status_code=422)
        else:
            _native_shader_args("status", {"shader": source,
                "project_context_witness": args.get("project_context_witness"), "request_id": args.get("request_id")})
        expected = ({"request_id", "project_context_witness", "action", "template_id"} if action == "new" else
                    {"request_id", "project_context_witness", "action", "source"} if action == "paste" else
                    {"request_id", "project_context_witness", "action", "shader", "expected_document_hash"})
        optional = {"space"} if action == "new" else {"title"} if action == "paste" else {"checkpoint_id"}
        valid = (expected <= set(args) and not set(args) - expected - optional and args.get("action") == action)
        if action == "new":
            valid = valid and args.get("template_id") == "hx_starter" and args.get("space", "direction_360") in {
                "direction_360", "equirect_map", "ray_360", "shadertoy_image"}
        elif action == "paste":
            try:
                source_bytes = args["source"].encode("utf-8", errors="strict") if type(args["source"]) is str else b""
            except UnicodeError:
                source_bytes = b""
            valid = valid and bool(source_bytes) and len(source_bytes) <= 2 * 1024 * 1024
            if "title" in args:
                valid = valid and type(args["title"]) is str and 1 <= len(args["title"]) <= 256
        else:
            valid = valid and type(args.get("expected_document_hash")) is str and bool(
                _WORKSPACE_DIGEST.fullmatch(args["expected_document_hash"]))
            if "checkpoint_id" in args:
                valid = valid and type(args["checkpoint_id"]) is str and bool(
                    re.fullmatch(r"[A-Za-z0-9_-]{1,128}", args["checkpoint_id"]))
        if not valid:
            raise HextileClientError("Invalid Shader creation", kind="other", status_code=422)
        try:
            result = self.request_json("POST", "/api/shaders/agent-operations/create", dict(args))
        except HextileClientError as exc:
            if exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError("Shader creation outcome unknown; read shader_get_operation by original request ID.",
                    kind="shader_operation_outcome_unknown", receipt={"request_id": args["request_id"],
                    **({"scope": "creation"} if action == "paste" else {"shader": source})}) from exc
            raise
        if type(result) is not dict or result.get("request_id") != args["request_id"] or result.get("operation") != (
                "shader_create_asset" if action in {"new", "paste"} else "shader_fork_asset"):
            raise HextileClientError("Shader creation acknowledgement unknown; read shader_get_operation.",
                kind="shader_operation_outcome_unknown", receipt={"request_id": args["request_id"],
                **({"scope": "creation"} if action == "paste" else {"shader": source})})
        if action == "paste":
            if not _valid_shader_creation_status(result, args, complete=True):
                raise HextileClientError("Shader Paste acknowledgement unknown; read original creation status.",
                    kind="shader_operation_outcome_unknown", receipt={"request_id": args["request_id"],
                    "scope": "creation"})
        return result

    def create_shader_asset(self, args: Mapping[str, Any]) -> dict:
        return self._create_shader_asset(args, "paste" if isinstance(args, Mapping)
                                         and args.get("action") == "paste" else "new")

    def fork_shader_asset(self, args: Mapping[str, Any]) -> dict:
        return self._create_shader_asset(args, "fork")

    def import_shader_bundle(self, args: Mapping[str, Any]) -> dict:
        required = {"request_id", "project_context_witness", "input_path", "collision_intent"}
        if (not isinstance(args, Mapping) or required - args.keys() or set(args) - required - {"bundle_sha256"}
                or args["collision_intent"] != "fork" or type(args["input_path"]) is not str
                or not _absolute_task_path(args["input_path"]) or Path(args["input_path"]).suffix.lower() != ".hexshader"
                or type(args["project_context_witness"]) is not str or not args["project_context_witness"]
                or "bundle_sha256" in args and (type(args["bundle_sha256"]) is not str
                    or _WORKSPACE_DIGEST.fullmatch(args["bundle_sha256"]) is None)):
            raise HextileClientError("Expected closed Shader Bundle task input", kind="other", status_code=422)
        try:
            valid_id = str(uuid.UUID(args["request_id"])) == args["request_id"] and uuid.UUID(args["request_id"]).version == 4
        except (ValueError, TypeError, AttributeError):
            valid_id = False
        if not valid_id:
            raise HextileClientError("Expected canonical request_id", kind="other", status_code=422)
        try:
            result = self.request_json("POST", "/api/shaders/agent-operations/import-bundle", dict(args))
        except HextileClientError as exc:
            if exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError("Shader Bundle import outcome unknown; read shader_get_operation by original request ID.",
                    kind="shader_operation_outcome_unknown", receipt={"request_id": args["request_id"]}) from exc
            raise
        if (not _valid_shader_creation_status(result, args, complete=False)
                or result["operation"] != "shader_import_bundle"
                or result["state"] == "saved" and "bundle_sha256" in args
                    and result["receipt"]["bundle_sha256"] != args["bundle_sha256"]):
            raise HextileClientError("Shader Bundle import acknowledgement unknown; read shader_get_operation.",
                kind="shader_operation_outcome_unknown", receipt={"request_id": args["request_id"]})
        return result

    def get_shader_operation(self, args: Mapping[str, Any]) -> Any:
        if (not isinstance(args, Mapping) or not {"request_id", "project_context_witness"} <= set(args)
                or set(args) - {"request_id", "project_context_witness", "shader", "scope"}):
            raise HextileClientError("Expected closed Shader operation lookup", status_code=422, kind="other")
        scope = args.get("scope", "asset")
        if scope not in {"asset", "creation", "library", "project", "output"} or (
                "shader" in args) != (scope in {"asset", "output"}):
            raise HextileClientError("Invalid Shader operation scope", status_code=422, kind="other")
        if scope in {"asset", "output"}:
            _native_shader_args("status", {key: args[key] for key in
                ("shader", "project_context_witness", "request_id")})
        else:
            try:
                valid = type(args["request_id"]) is str and str(uuid.UUID(args["request_id"])) == args["request_id"] and uuid.UUID(args["request_id"]).version == 4
            except (ValueError, AttributeError):
                valid = False
            if not valid or type(args["project_context_witness"]) is not str or not args["project_context_witness"]:
                raise HextileClientError("Invalid Shader operation scope", status_code=422, kind="other")
        result = self.request_json("GET", f"/api/shaders/agent-operations/operations/{args['request_id']}",
            params={**({"origin": args["shader"]["origin"], "shader_id": args["shader"]["shaderId"]}
                       if "shader" in args else {}), "scope": scope,
                    "project_context_witness": args["project_context_witness"]})
        if scope == "creation" and not _valid_shader_creation_status(result, args, complete=False):
            raise HextileClientError("Invalid Shader creation status", kind="other")
        if scope == "output":
            expected = {"schema", "request_id", "operation", "state", "shader",
                        "project_context_witness", "scope"}
            try:
                bounded = len(json.dumps(result, ensure_ascii=False,
                                         allow_nan=False).encode("utf-8")) <= 65536
            except (TypeError, ValueError, OverflowError):
                bounded = False
            if (type(result) is not dict or not expected <= set(result)
                    or set(result) - expected - {"receipt", "reason", "output_path", "destination_project"}
                    or result["schema"] != 1 or result["request_id"] != args["request_id"]
                    or result["scope"] != "output" or result["shader"] != args["shader"]
                    or result["project_context_witness"] != args["project_context_witness"]
                    or type(result["operation"]) is not str
                    or result["operation"] not in {"shader_export_bundle", "shader_export_to_project"}
                    or type(result["state"]) is not str
                    or result["state"] not in {"unknown", "saved", "applied", "refused"}
                    or not bounded):
                raise HextileClientError("Invalid Shader output status", kind="other")
            if "receipt" in result:
                _shader_output_receipt("bundle" if result["operation"] == "shader_export_bundle"
                                       else "project", args, result["receipt"])
        return result

    def get_shader_credits(self, args: Mapping[str, Any]) -> dict:
        if not isinstance(args, Mapping) or set(args) - {
                "shader", "project_context_witness", "section", "cursor", "limit",
                "text_ref", "offset_utf8"}:
            raise HextileClientError("Expected closed Shader credits page", status_code=422, kind="other")
        _native_read_args({key: args[key] for key in ("shader", "project_context_witness", "lease_id") if key in args},
                          {"shader", "project_context_witness"})
        if (args.get("section", "sources") not in {"sources", "contributors", "current_roles", "history",
                                                          "retained_credits", "notices", "text"}
                or ("text_ref" in args and (args.get("section") != "text" or type(args["text_ref"]) is not str
                     or re.fullmatch(r"ct1:sha256:[0-9a-f]{64}:(top|notices|retained_credits):[0-9]+:[a-z_]+", args["text_ref"]) is None))
                or (args.get("section") == "text" and "text_ref" not in args)
                or ("offset_utf8" in args and ("text_ref" not in args or type(args["offset_utf8"]) is not int
                     or args["offset_utf8"] < 0))
                or ("cursor" in args and (type(args["cursor"]) is not int or args["cursor"] < 0))
                or ("limit" in args and (type(args["limit"]) is not int or not 1 <= args["limit"] <= 32))):
            raise HextileClientError("Invalid Shader credits page", status_code=422, kind="other")
        params = {"origin": args["shader"]["origin"], "shader_id": args["shader"]["shaderId"],
                  "project_context_witness": args["project_context_witness"]}
        params.update({key: args[key] for key in ("section", "cursor", "limit", "text_ref", "offset_utf8") if key in args})
        result = self.request_json("GET", "/api/shaders/agent-operations/credits", params=params)
        allowed = {"schema", "target", "provenance_hash", "author", "attribution", "license",
                   "automatic_credit", "section", "cursor", "total", "next_cursor",
                   "protected_distribution_present", "has_opaque_fields", "truncated_fields",
                   "oversized_row", "sources", "contributors", "current_roles", "history",
                   "retained_credits", "notices", "base", "working_digest", "text_fields",
                   "text_ref", "offset_utf8", "text", "total_bytes", "next_offset_utf8",
                   "original_source_hash", "distribution"}
        distribution = result.get("distribution") if type(result) is dict else None
        valid_distribution = True
        if distribution is not None:
            valid_distribution = type(distribution) is dict
            if valid_distribution and set(distribution) >= {"schema", "rights", "source_hash",
                    "original_sha256", "licenses_total"}:
                valid_distribution = (set(distribution) <= {"schema", "rights", "source_hash",
                    "original_sha256", "licenses_total", "has_opaque_fields"}
                    and distribution["schema"] == 1
                    and distribution["rights"] in {"declared", "unresolved"}
                    and type(distribution["source_hash"]) is str
                    and _WORKSPACE_DIGEST.fullmatch(distribution["source_hash"]) is not None
                    and (distribution["original_sha256"] is None or
                         type(distribution["original_sha256"]) is str and
                         _WORKSPACE_DIGEST.fullmatch(distribution["original_sha256"]) is not None)
                    and type(distribution["licenses_total"]) is int and 0 <= distribution["licenses_total"] <= 100000
                    and ("has_opaque_fields" not in distribution or distribution["has_opaque_fields"] is True))
            elif valid_distribution:
                valid_distribution = (distribution == {"has_opaque_fields": True}
                    or set(distribution) == {"schema", "has_opaque_fields"}
                    and type(distribution["schema"]) is int and distribution["schema"] > 0
                    and distribution["has_opaque_fields"] is True)
        if (type(result) is not dict or set(result) - allowed or result.get("schema") != 1
                or result.get("target") != args["shader"]
                or result.get("section") != args.get("section", "sources")
                or (result["section"] == "text" and (result.get("text_ref") != args.get("text_ref")
                    or result.get("offset_utf8") != args.get("offset_utf8", 0)
                    or type(result.get("text")) is not str or type(result.get("total_bytes")) is not int
                    or (result.get("next_offset_utf8") is not None and type(result.get("next_offset_utf8")) is not int)))
                or (result["section"] != "text" and (type(result.get(result["section"])) is not list
                    or len(result[result["section"]]) > 32))
                or not valid_distribution
                or ("original_source_hash" in result and (type(result["original_source_hash"]) is not str
                    or _WORKSPACE_DIGEST.fullmatch(result["original_source_hash"]) is None))
                or (result.get("section") == "text" and ("distribution" in result or "original_source_hash" in result))
                or len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 60 * 1024
                or "source" in result or "mutation" in result or "ticket_id" in result):
            raise HextileClientError("Malformed Shader credits result", kind="other")
        return result

    def propose_shader_credits(self, args: Mapping[str, Any]) -> dict:
        required = {"shader", "project_context_witness", "request_id", "base",
                    "working_digest", "expected_provenance_hash", "changes"}
        if not isinstance(args, Mapping) or set(args) != required:
            raise HextileClientError("Expected closed Shader credits proposal", status_code=422, kind="other")
        _native_shader_args("status", {key: args[key] for key in ("shader", "project_context_witness", "request_id")})
        base = args["base"]
        if (type(base) is not dict or set(base) != {"kind", "working_revision", "document_hash", "source_hash"}
                or base["kind"] != "saved" or type(base["working_revision"]) is not int
                or base["working_revision"] < 1 or any(type(base[key]) is not str or
                    _WORKSPACE_DIGEST.fullmatch(base[key]) is None for key in ("document_hash", "source_hash"))
                or any(args[key] is not None and (type(args[key]) is not str or
                    _WORKSPACE_DIGEST.fullmatch(args[key]) is None)
                       for key in ("working_digest", "expected_provenance_hash"))
                or not _credit_changes(args["changes"])
                or len(json.dumps(dict(args), ensure_ascii=False).encode("utf-8")) > 60 * 1024):
            raise HextileClientError("Invalid Shader credits proposal", status_code=422, kind="other")
        request_id = args["request_id"]
        try:
            result = self.request_json("POST", "/api/shaders/agent-operations/credits/proposals", dict(args))
        except HextileClientError as exc:
            if exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError("Credits proposal outcome unknown; read shader_get_operation by request_id.",
                                         kind="shader_operation_outcome_unknown", receipt={"request_id": request_id}) from exc
            raise
        if (type(result) is not dict or set(result) - {"schema", "proposal_id", "request_id", "state",
                "shader", "project_context_witness", "expected_provenance_hash", "mutation_hash"}
                or result.get("request_id") != request_id
                or result.get("state") not in {"pending", "applied", "saved", "refused", "expired", "unknown"}
                or "ticket_id" in result or "mutation" in result or "provenance" in result
                or len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 32768):
            raise HextileClientError("Credits proposal acknowledgement unknown; read shader_get_operation.",
                                     kind="shader_operation_outcome_unknown", receipt={"request_id": request_id})
        return result

    def research_shader_sources(self, args: Mapping[str, Any]) -> dict:
        _native_read_args(args, {"shader", "project_context_witness", "source_url"}, {"links"})
        links = args.get("links", [])
        if (type(args["source_url"]) is not str or not 1 <= len(args["source_url"].encode("utf-8")) <= 2048
                or type(links) is not list or len(links) > 4
                or any(type(link) is not str or len(link.encode("utf-8")) > 2048 for link in links)):
            raise HextileClientError("Invalid source research URLs", status_code=422, kind="other")
        result = self.request_json("POST", "/api/shaders/agent-operations/research-sources", dict(args))
        if (type(result) is not dict or set(result) - {"schema", "pages", "omitted_links", "omitted_bytes", "limits"}
                or result.get("schema") != 1 or type(result.get("pages")) is not list
                or len(result["pages"]) > 5 or len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 60 * 1024
                or "source" in result or "ticket_id" in result):
            raise HextileClientError("Malformed source research result", kind="other")
        return result

    def _shader_workspace_request(self, method: str, path: str, body: Optional[Mapping[str, Any]] = None,
                                  *, params: Optional[Mapping[str, Any]] = None) -> Any:
        """Proxy once. An uncertain reply never becomes a receipt or automatic retry."""
        try:
            return self.request_json(method, path, body, params=params,
                                     timeout=15.0 if path.endswith("/open") else None,
                                     headers={"X-Hextile-Agent": "mcp"})
        except http.client.HTTPException as exc:
            raise HextileClientError("Shader workspace outcome unknown; rediscover current authority before retrying.",
                                     kind="workspace_outcome_unknown") from exc
        except HextileClientError as exc:
            if exc.kind == "other" and exc.status_code is not None and 200 <= exc.status_code < 300:
                raise HextileClientError("Shader workspace acknowledgement unknown; rediscover current authority before retrying.",
                                         kind="workspace_outcome_unknown", status_code=exc.status_code) from exc
            try:
                detail = json.loads(exc.body or "{}").get("detail")
            except (ValueError, AttributeError):
                detail = None
            if isinstance(detail, dict):
                exc.receipt = detail
            if exc.status_code == 404 and detail == "Not Found":
                raise HextileClientError("Upgrade 360 Hextile to a version with Shader workspaces, then retry.",
                                         kind="upgrade", status_code=404, body=exc.body) from exc
            raise

    def open_shader_workspace(self, body: Mapping[str, Any]) -> Any:
        validate_shader_workspace("open", body)
        result = self._shader_workspace_request("POST", "/api/agent/shader-workspaces/open", dict(body))
        if (not isinstance(result, dict) or type(result.get("handle")) is not str
                or _WORKSPACE_HANDLE.fullmatch(result["handle"]) is None
                or type(result.get("generation")) is not int or not 0 <= result["generation"] <= MAX_WORKSPACE_GENERATION
                or type(result.get("content_digest")) is not str or _WORKSPACE_DIGEST.fullmatch(result["content_digest"]) is None
                or result.get("shader") != body["shader"]
                or result.get("project_context_witness") != body["project_context_witness"]
                or result.get("studio_surface_id") != body["studio_surface_id"]
                or result.get("attachment_state", "attached") != "attached"
                or (body.get("workspace_schema") != 2 and (
                    type(result.get("files")) is not dict or set(result["files"]) != {"source_path", "authoring_path"}
                    or any(type(value) is not str or not value for value in result["files"].values())))):
            raise HextileClientError("Shader workspace acknowledgement unknown; rediscover or make one identical open retry. No paths were released.",
                                     kind="workspace_outcome_unknown")
        if body.get("workspace_schema") == 2 and (
                result.get("workspace_schema") != 2 or type(result.get("files")) is not list
                or not result["files"] or len(result["files"]) > 32
                or any(type(row) is not dict or set(row) != {"path", "native_path"}
                       or any(type(value) is not str or not value for value in row.values()) for row in result["files"])
                or any(type(result.get(key)) is not str or not result[key] for key in ("workspace_root", "authoring_path"))):
            raise HextileClientError("Upgrade 360 Hextile and reconnect for workspace_schema 2; no workspace paths were released.",
                                     kind="upgrade")
        return result

    def register_shader_update(self, args: Mapping[str, Any]) -> Any:
        validate_shader_workspace("register", args)
        handle = urllib.parse.quote(args["handle"], safe="")
        body = {key: args[key] for key in ("change_id", "expected_generation", "content_digest")}
        if "attribution_action" in args:
            body["attribution_action"] = args["attribution_action"]
        if "source_proposal" in args:
            body["source_proposal"] = args["source_proposal"]
        result = self._shader_workspace_request("POST", f"/api/agent/shader-workspaces/{handle}/updates", body)
        if (not isinstance(result, dict) or result.get("handle") != args["handle"]
                or result.get("change_id") != args["change_id"]
                or result.get("content_digest") != args["content_digest"]
                or type(result.get("generation")) is not int
                or not 0 <= result["generation"] <= MAX_WORKSPACE_GENERATION
                or type(result.get("candidate_id")) is not str or not result["candidate_id"]):
            raise HextileClientError(
                "Shader workspace registration acknowledgement unknown; read the current receipt before retrying.",
                kind="workspace_outcome_unknown")
        return result

    def get_shader_update(self, args: Mapping[str, Any]) -> Any:
        validate_shader_workspace("get", args)
        handle = urllib.parse.quote(args["handle"], safe="")
        change_id = urllib.parse.quote(args["change_id"], safe="")
        params = {"project_context_witness": args["project_context_witness"]}
        if args.get("include_source_diagnostics") is True:
            params["include_source_diagnostics"] = "true"
        result = self._shader_workspace_request("GET", f"/api/agent/shader-workspaces/{handle}/updates/{change_id}", params=params)
        if args.get("include_source_diagnostics") is True and (
                not isinstance(result, dict) or type(result.get("source_diagnostics")) is not list):
            raise HextileClientError("Upgrade 360 Hextile and reconnect for bounded source diagnostics; this APP did not acknowledge support.",
                                     kind="upgrade")
        return result

    @staticmethod
    def _recovery_result(data: Any, allowed: set[str], required: set[str]) -> dict:
        try:
            size = len(json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        except (TypeError, ValueError, UnicodeError) as exc:
            raise HextileClientError("Malformed Shader recovery receipt", kind="other") from exc
        if type(data) is not dict or size > 32768 or required - set(data) or set(data) - allowed:
            raise HextileClientError("Malformed or unbounded Shader recovery receipt", kind="other")
        return data

    @staticmethod
    def _workspace_recovery_args(args: Mapping[str, Any], operation: str) -> None:
        base = {"handle", "project_context_witness"}
        required = (base if operation == "get" else
                    base | {"change_id", "generation", "content_digest", "studio_surface_id"}
                    if operation == "recheck" else base | {"generation", "studio_surface_id"})
        optional = {"change_id"} if operation == "get" else set()
        if not isinstance(args, Mapping) or required - args.keys() or set(args) - required - optional:
            raise HextileClientError("Expected closed Shader recovery arguments", kind="other", status_code=422)
        handle = args["handle"]
        if (type(handle) is not str or _WORKSPACE_HANDLE.fullmatch(handle) is None or
                type(args["project_context_witness"]) is not str or
                not 1 <= len(args["project_context_witness"]) <= 256):
            raise HextileClientError("Invalid Shader recovery identity", kind="other", status_code=422)
        if "change_id" in args:
            change_id = args["change_id"]
            suffix = change_id[len(handle) + 1:] if type(change_id) is str and change_id.startswith(handle + ":") else ""
            if (type(change_id) is not str or len(change_id) > 81 or
                    _WORKSPACE_SUFFIX.fullmatch(suffix) is None or int(suffix) > MAX_WORKSPACE_GENERATION):
                raise HextileClientError("Invalid Shader change identity", kind="other", status_code=422)
        if operation in {"recheck", "stop"}:
            if (type(args["generation"]) is not int or not 0 <= args["generation"] <= MAX_WORKSPACE_GENERATION or
                    type(args["studio_surface_id"]) is not str or not 1 <= len(args["studio_surface_id"]) <= 256):
                raise HextileClientError("Invalid Shader recovery generation", kind="other", status_code=422)
        if operation == "recheck" and (type(args["content_digest"]) is not str or
                                       _WORKSPACE_DIGEST.fullmatch(args["content_digest"]) is None):
            raise HextileClientError("Invalid Shader recovery digest", kind="other", status_code=422)

    def get_shader_proposal_status(self, args: Mapping[str, Any]) -> dict:
        if (not isinstance(args, Mapping) or set(args) != {"ticket_id", "project_context_witness"} or
                type(args["ticket_id"]) is not str or not re.fullmatch(r"spt_[0-9a-f]{32}", args["ticket_id"]) or
                type(args["project_context_witness"]) is not str or not 1 <= len(args["project_context_witness"]) <= 256):
            raise HextileClientError("Expected closed Shader proposal identity", kind="other", status_code=422)
        ticket = self.request_json("GET", f"/api/agent/shader-proposals/{args['ticket_id']}",
                                   headers={"X-Hextile-Agent": "mcp",
                                            "X-Hextile-Project-Witness": args["project_context_witness"]})
        if type(ticket) is not dict or ticket.get("ticket_id") != args["ticket_id"]:
            raise HextileClientError("Malformed Shader proposal status", kind="other")
        visible = {"ticket_id", "kind", "shader", "project_context_witness", "base", "identity",
                   "ready", "cancelled", "result", "board_id", "candidates"}
        if type(ticket.get("ready")) is not bool or ticket.get("project_context_witness") != args["project_context_witness"]:
            raise HextileClientError("Malformed Shader proposal status", kind="other")
        return self._recovery_result({key: ticket[key] for key in visible if key in ticket},
                                     visible, {"ticket_id", "ready", "project_context_witness"})

    def get_shader_workspace_status(self, args: Mapping[str, Any]) -> dict:
        self._workspace_recovery_args(args, "get")
        handle = args["handle"]
        witness = args["project_context_witness"]
        attachment = self._shader_workspace_request("GET", f"/api/agent/shader-workspaces/{handle}/attachment",
                                                    params={"project_context_witness": witness})
        attachment = self._recovery_result(attachment,
            {"handle", "generation", "attachment_state", "studio_surface_id", "mount_generation",
             "project_context_witness", "base", "candidate_id", "change_id", "activity"},
            {"handle", "generation", "attachment_state", "studio_surface_id", "project_context_witness"})
        if attachment["handle"] != handle or attachment["project_context_witness"] != witness:
            raise HextileClientError("Shader attachment identity changed", kind="workspace_outcome_unknown")
        change_id = args.get("change_id") or attachment.get("change_id")
        receipt = None
        if change_id is not None:
            raw = self.get_shader_update({"handle": handle, "change_id": change_id,
                                          "project_context_witness": witness})
            allowed = {"handle", "change_id", "candidate_id", "generation", "content_digest", "shader",
                       "base", "project_context_witness", "studio_surface_id", "check_attempt",
                       "attachment_state", "prepare", "compile", "preview", "presentation", "save",
                       "check_deadline_at", "next_poll_ms", "reason", "saved", "diagnostics",
                       "attribution_outcome"}
            raw = self._recovery_result(raw, allowed | {"raw_log"},
                                        {"handle", "change_id", "candidate_id", "generation",
                                         "content_digest", "check_attempt", "save"})
            if (raw["handle"] != handle or raw["change_id"] != change_id or
                    raw.get("project_context_witness") != witness or
                    raw.get("studio_surface_id") != attachment["studio_surface_id"] or
                    type(raw["generation"]) is not int or raw["generation"] > attachment["generation"] or
                    (attachment.get("change_id") == change_id and
                     attachment.get("candidate_id") != raw["candidate_id"])):
                raise HextileClientError("Shader workspace changed during recovery; read again",
                                         kind="workspace_outcome_unknown")
            receipt = {key: raw[key] for key in allowed if key in raw and key != "diagnostics"}
        return self._recovery_result({"schema": 1, "attachment": {key: attachment[key] for key in attachment
            if key != "activity"}, "receipt": receipt}, {"schema", "attachment", "receipt"},
            {"schema", "attachment", "receipt"})

    def recheck_shader_update(self, args: Mapping[str, Any]) -> dict:
        self._workspace_recovery_args(args, "recheck")
        handle, change_id = args["handle"], args["change_id"]
        body = {key: args[key] for key in ("generation", "content_digest", "studio_surface_id",
                                           "project_context_witness")}
        try:
            result = self._shader_workspace_request("POST",
                f"/api/agent/shader-workspaces/{handle}/updates/{urllib.parse.quote(change_id, safe='')}/recheck", body)
        except HextileClientError as exc:
            if exc.kind in {"app_down", "workspace_outcome_unknown"} or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError("Shader recheck outcome unknown; read the same workspace and change before any retry.",
                                         kind="workspace_outcome_unknown",
                                         receipt={"handle": handle, "change_id": change_id}) from exc
            raise
        result = self._recovery_result(result,
            {"handle", "change_id", "candidate_id", "generation", "content_digest", "shader", "base",
             "project_context_witness", "studio_surface_id", "check_attempt", "attachment_state", "prepare",
             "compile", "preview", "presentation", "save", "diagnostics", "reason", "saved",
             "check_deadline_at", "next_poll_ms", "attribution_outcome"},
            {"handle", "change_id", "candidate_id", "generation", "content_digest", "check_attempt"})
        if (result["handle"] != handle or result["change_id"] != change_id or
                result["generation"] != args["generation"] or result["content_digest"] != args["content_digest"] or
                result.get("studio_surface_id") != args["studio_surface_id"] or
                result.get("project_context_witness") != args["project_context_witness"]):
            raise HextileClientError("Shader recheck acknowledgement unknown; read the original change",
                                     kind="workspace_outcome_unknown",
                                     receipt={"handle": handle, "change_id": change_id})
        return {key: value for key, value in result.items() if key != "diagnostics"}

    def stop_shader_workspace(self, args: Mapping[str, Any]) -> dict:
        self._workspace_recovery_args(args, "stop")
        handle = args["handle"]
        body = {key: args[key] for key in ("generation", "studio_surface_id", "project_context_witness")}
        try:
            result = self._shader_workspace_request("DELETE", f"/api/agent/shader-workspaces/{handle}", body)
        except HextileClientError as exc:
            if exc.kind in {"app_down", "workspace_outcome_unknown"} or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError("Shader stop outcome unknown; read the same workspace before any retry.",
                                         kind="workspace_outcome_unknown", receipt={"handle": handle}) from exc
            raise
        result = self._recovery_result(result,
            {"handle", "generation", "attachment_state", "studio_surface_id", "mount_generation",
             "project_context_witness", "base"},
            {"handle", "generation", "attachment_state", "studio_surface_id", "project_context_witness"})
        if (result["handle"] != handle or result["generation"] != args["generation"] or
                result["project_context_witness"] != args["project_context_witness"] or
                result["studio_surface_id"] != args["studio_surface_id"] or
                result["attachment_state"] != "stopped"):
            raise HextileClientError("Shader stop acknowledgement unknown; read workspace status",
                                     kind="workspace_outcome_unknown")
        return result

    def get_live_context(
        self,
        *,
        include_nav: bool = False,
        include_active_tool: bool = False,
    ) -> Any:
        """GET /api/agent/live-context. No local merge."""
        return self.get_json(
            "/api/agent/live-context",
            params={
                "include_nav": 1 if include_nav else 0,
                "include_active_tool": 1 if include_active_tool else 0,
            },
        )

    def save_workflow(
        self,
        origin: str,
        workflow_id: str,
        document: Mapping[str, Any],
    ) -> Any:
        """POST /api/workflows/{origin} — create-only on user|project."""
        origin_s = str(origin or "")
        if origin_s == "builtin":
            raise HextileClientError(
                "Built-in workflows are immutable. Save to origin=user or origin=project.",
                status_code=403,
                kind="http",
            )
        if origin_s not in ("user", "project"):
            raise HextileClientError(
                "origin must be 'user' or 'project'",
                status_code=None,
                kind="other",
            )
        if not workflow_id:
            raise HextileClientError(
                "id is required", status_code=None, kind="other"
            )
        if not isinstance(document, Mapping):
            raise HextileClientError(
                "document must be a JSON object", status_code=None, kind="other"
            )
        o = urllib.parse.quote(origin_s, safe="")
        return self.post_json(
            f"/api/workflows/{o}",
            {"id": str(workflow_id), "document": dict(document)},
        )

    def delete_workflow(self, origin: str, workflow_id: str) -> Any:
        """DELETE /api/workflows/{origin}/{id} — user|project only."""
        origin_s = str(origin or "")
        if origin_s == "builtin":
            raise HextileClientError(
                "Built-in workflows are immutable. Delete only origin=user or origin=project.",
                status_code=403,
                kind="http",
            )
        if origin_s not in ("user", "project"):
            raise HextileClientError(
                "origin must be 'user' or 'project'",
                status_code=None,
                kind="other",
            )
        if not workflow_id:
            raise HextileClientError(
                "id is required", status_code=None, kind="other"
            )
        o = urllib.parse.quote(origin_s, safe="")
        wid = urllib.parse.quote(str(workflow_id), safe="")
        return self.delete_json(f"/api/workflows/{o}/{wid}")

    def run_workflow(
        self,
        *,
        workflow_id: Optional[str] = None,
        origin: str = "builtin",
        document: Optional[dict[str, Any]] = None,
        overrides: Optional[dict[str, Any]] = None,
        output: Optional[dict[str, Any]] = None,
        dry_run: bool = False,
    ) -> Any:
        """POST /api/workflows/run (merge + validate [+ queue])."""
        body: dict[str, Any] = {"origin": origin, "dry_run": dry_run}
        if workflow_id is not None:
            body["workflow_id"] = workflow_id
        if document is not None:
            body["document"] = document
        if overrides is not None:
            body["overrides"] = overrides
        if output is not None:
            body["output"] = output
        return self.post_json(
            "/api/workflows/run",
            body,
            headers=None if self.internal_mode else {"X-Hextile-Agent": "mcp"},
        )

    def dry_run_workflow(self, **kwargs: Any) -> Any:
        """POST /api/workflows/run with dry_run=true."""
        kwargs["dry_run"] = True
        return self.run_workflow(**kwargs)

    # ── renders ─────────────────────────────────────────────────────────

    def get_gpu_diagnostics(self) -> Any:
        """GET /api/processors/vram-status; the app owns GPU measurements."""
        return self.get_json("/api/processors/vram-status")

    def get_status(self, run_id: str) -> Any:
        """GET /api/renders/{run_id}."""
        rid = urllib.parse.quote(run_id, safe="")
        return self.get_json(f"/api/renders/{rid}")

    def get_render_config(self, render_id: str) -> Any:
        """GET /api/renders/{render_id}/config — parsed canonical JSON."""
        rid = urllib.parse.quote(render_id, safe="")
        return self.get_json(f"/api/renders/{rid}/config")

    def get_logs(self, run_id: str) -> Any:
        """GET /api/renders/{run_id}/logs."""
        rid = urllib.parse.quote(run_id, safe="")
        return self.get_json(f"/api/renders/{rid}/logs")

    def cancel_run(self, run_id: str) -> Any:
        """POST /api/renders/{run_id}/stop → cancelled."""
        rid = urllib.parse.quote(run_id, safe="")
        return self.post_json(f"/api/renders/{rid}/stop")

    def retry_run(self, run_id: str, *, vram_recovery: bool = False) -> Any:
        """POST retry; request render-scoped idle-holder recovery only when true."""
        rid = urllib.parse.quote(run_id, safe="")
        return self.post_json(
            f"/api/renders/{rid}/retry",
            {"vram_recovery": True} if vram_recovery else None,
        )

    def list_runs(self, lifecycle_status: str = "active") -> Any:
        """GET /api/renders/?lifecycle_status= (default active)."""
        status = lifecycle_status or "active"
        return self.get_json(
            "/api/renders/",
            params={"lifecycle_status": status},
        )

    def search_library_prompts(self, body: Mapping[str, Any]) -> Any:
        """POST a bounded render/sequence prompt search page."""
        return self.post_json("/api/renders/library-prompts/search", body)

    # ── sequences ───────────────────────────────────────────────────────

    def extract_sequence_video(self, video_path: str) -> Any:
        """POST /api/sequences/extract-video {video_path}."""
        return self.post_json(
            "/api/sequences/extract-video",
            {"video_path": video_path},
            timeout=LONG_OPERATION_TIMEOUT_S,
        )

    def create_sequence(
        self,
        folder_path: str,
        config: Mapping[str, Any],
        name: Optional[str] = None,
    ) -> Any:
        """POST /api/sequences/create — folder_path + full config. No local merge."""
        if not isinstance(config, Mapping):
            raise HextileClientError(
                "config must be a JSON object",
                status_code=None,
                kind="other",
            )
        body: dict[str, Any] = {
            "folder_path": folder_path,
            "config": dict(config),
        }
        if name is not None:
            body["name"] = name
        return self.post_json("/api/sequences/create", body)

    def start_sequence(self, sequence_id: str) -> Any:
        """POST /api/sequences/{sequence_id}/start."""
        sid = urllib.parse.quote(sequence_id, safe="")
        return self.post_json(f"/api/sequences/{sid}/start")

    def get_sequence(self, sequence_id: str) -> Any:
        """GET /api/sequences/{sequence_id}."""
        sid = urllib.parse.quote(sequence_id, safe="")
        return self.get_json(f"/api/sequences/{sid}")

    def list_sequences(self, lifecycle_status: str = "active") -> Any:
        """GET /api/sequences/?lifecycle_status= (default active)."""
        status = lifecycle_status or "active"
        return self.get_json(
            "/api/sequences/",
            params={"lifecycle_status": status},
        )

    def stop_sequence(self, sequence_id: str) -> Any:
        """POST /api/sequences/{sequence_id}/stop."""
        sid = urllib.parse.quote(sequence_id, safe="")
        return self.post_json(f"/api/sequences/{sid}/stop")

    # ── seed ────────────────────────────────────────────────────────────

    def get_seed_memory_advice(
        self, lora_path: str, width: int, height: int, *, cpu_offload: bool = False
    ) -> Any:
        """Read two independent APP samples; neither reserves VRAM."""
        gpu = self.get_gpu_diagnostics()
        advice = self.get_json(
            "/api/360-lora/memory-advice",
            params={
                "lora_path": lora_path,
                "width": width,
                "height": height,
                "cpu_offload": cpu_offload,
            },
        )
        return {"sampling": "separate", "gpu": gpu, "advice": advice}

    def generate_seed(
        self,
        prompt: str,
        *,
        request_id: str,
        lora_path: str,
        base_model: str,
        n: int = 4,
        **extra: Any,
    ) -> Any:
        """Submit one idempotent 360-LoRA job; return its short acknowledgement."""
        try:
            if str(uuid.UUID(request_id)) != request_id:
                raise ValueError("noncanonical UUID")
        except (TypeError, ValueError, AttributeError) as exc:
            raise HextileClientError(
                "request_id must be a canonical UUID", kind="other"
            ) from exc
        body: dict[str, Any] = {
            "request_id": request_id,
            "prompt": prompt,
            "lora_path": lora_path,
            "base_model": base_model,
            "num_variations": n,
        }
        body.update(extra)
        try:
            return self.post_json("/api/360-lora/jobs", body)
        except HextileClientError as exc:
            if exc.kind != "app_down":
                raise
            raise HextileClientError(
                f"Seed acknowledgement unknown for job_id {request_id}. "
                "Call get_seed_job with this ID; replay only the same request body and ID if needed.",
                status_code=exc.status_code,
                body=exc.body,
                kind=exc.kind,
            ) from exc

    def get_seed_job(self, job_id: str) -> Any:
        """GET exact job status, progress, original-index results, and errors."""
        jid = urllib.parse.quote(job_id, safe="")
        return self.get_json(f"/api/360-lora/jobs/{jid}")

    def list_seed_history(
        self,
        offset: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> Any:
        """GET /api/360-lora/history — always send offset+limit for {batches, total}."""
        params: dict[str, Any] = {"offset": int(offset), "limit": int(limit)}
        if status:
            params["status"] = status
        return self.get_json("/api/360-lora/history", params=params)

    def get_seed_batch(self, batch_id: str) -> Any:
        """GET /api/360-lora/history/{batch_id}."""
        bid = urllib.parse.quote(batch_id, safe="")
        return self.get_json(f"/api/360-lora/history/{bid}")

    def cancel_seed(self, job_id: str) -> Any:
        """POST job-scoped cancel; never cancel a different seed job."""
        jid = urllib.parse.quote(job_id, safe="")
        return self.post_json(f"/api/360-lora/jobs/{jid}/cancel")

    def list_360_loras(self) -> Any:
        """GET /api/360-lora/loras — catalog for generate_seed path + base_model."""
        return self.get_json("/api/360-lora/loras")

    # ── models ──────────────────────────────────────────────────────────

    def list_installed_models(self, pipeline_id: Optional[str] = None) -> Any:
        """GET /api/models/{pipeline_id}?installed_only=true, or catalog/status."""
        pid = str(pipeline_id).strip() if pipeline_id else ""
        if pid:
            quoted = urllib.parse.quote(pid, safe="")
            return self.get_json(
                f"/api/models/{quoted}",
                params={"installed_only": "true"},
            )
        status = self.get_json("/api/models/catalog/status")
        note = "Pass pipeline_id to list installed weights for that pipeline."
        if isinstance(status, dict):
            out = dict(status)
            out["note"] = note
            return out
        return {"catalog_status": status, "note": note}

    def get_model_readiness(self, overrides: list[Mapping[str, Any]]) -> Any:
        return self.post_json("/api/models/selection-catalog", {"overrides": overrides})

    def get_model_download_queue(self) -> Any:
        return self.get_json("/api/models/queue")

    def _model_mutation(self, path: str, body: Optional[Mapping[str, Any]] = None,
                        *, params: Optional[Mapping[str, Any]] = None,
                        bundle: bool = False) -> Any:
        try:
            result = self.post_json(path, body, params=params)
            if (not isinstance(result, dict)
                    or type(result.get("success")) is not bool
                    or not isinstance(result.get("message"), str)
                    or (bundle and (not isinstance(result.get("model_dispositions"), dict)
                                    or not isinstance(result.get("failed_model_ids"), list)))):
                raise HextileClientError(
                    "Model queue action outcome unknown; read the download queue before any repeat.",
                    kind="model_outcome_unknown",
                )
            return result
        except http.client.HTTPException as exc:
            raise HextileClientError(
                "Model queue action outcome unknown; read the download queue before any repeat.",
                body=str(exc), kind="model_outcome_unknown",
            ) from exc
        except HextileClientError as exc:
            if exc.kind == "app_down" or (
                exc.kind == "other" and exc.status_code is not None
                and 200 <= exc.status_code < 300
            ):
                raise HextileClientError(
                    "Model queue action outcome unknown; read the download queue before any repeat.",
                    body=exc.body, kind="model_outcome_unknown",
                ) from exc
            raise

    def install_model_single(self, pipeline_id: str, model_id: str) -> Any:
        return self._model_mutation("/api/models/queue/add", {
            "pipeline_id": pipeline_id, "model_id": model_id,
        })

    def install_model_bundle(self, pipeline_id: str, model_id: str,
                             expected_selection_fingerprint: str) -> Any:
        pid = urllib.parse.quote(pipeline_id, safe="")
        return self._model_mutation(
            f"/api/models/queue/pipeline/{pid}",
            params={"selected_model_id": model_id,
                    "expected_selection_fingerprint": expected_selection_fingerprint},
            bundle=True,
        )

    def repair_model(self, pipeline_id: str, model_id: str) -> Any:
        pid = urllib.parse.quote(pipeline_id, safe="")
        mid = urllib.parse.quote(model_id, safe="")
        return self._model_mutation(f"/api/models/{pid}/{mid}/repair")

    def cancel_model_download(self, pipeline_id: str, model_id: str,
                              expected_queue_entry_id: str) -> Any:
        pid = urllib.parse.quote(pipeline_id, safe="")
        mid = urllib.parse.quote(model_id, safe="")
        return self._model_mutation(
            f"/api/models/{pid}/{mid}/cancel",
            params={"expected_queue_entry_id": expected_queue_entry_id},
        )

    # ── batch workflows (thin HTTP; no Batch UUID in Render activity) ──

    def preflight_batch(self, body: Mapping[str, Any]) -> Any:
        """POST /api/batch-workflows/preflight — returns promptly (scan is async)."""
        if not isinstance(body, Mapping):
            raise HextileClientError(
                "preflight body must be a JSON object",
                status_code=None,
                kind="other",
            )
        return self.post_json(
            "/api/batch-workflows/preflight",
            dict(body),
            headers={"X-Hextile-Agent": "mcp"},
        )

    def get_batch_preflight(
        self,
        preflight_id: str,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Any:
        """GET /api/batch-workflows/preflights/{id}?cursor=&limit=."""
        if not preflight_id:
            raise HextileClientError(
                "preflight_id is required", status_code=None, kind="other"
            )
        pid = urllib.parse.quote(str(preflight_id), safe="")
        params: dict[str, Any] = {}
        if cursor:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = int(limit)
        return self.get_json(
            f"/api/batch-workflows/preflights/{pid}",
            params=params or None,
        )

    def start_batch(
        self,
        *,
        preflight_id: str,
        spec_hash: str,
        idempotency_key: str,
    ) -> Any:
        """POST /api/batch-workflows {preflight_id, spec_hash, idempotency_key}."""
        if not preflight_id or not spec_hash or not idempotency_key:
            raise HextileClientError(
                "preflight_id, spec_hash, and idempotency_key are required",
                status_code=None,
                kind="other",
            )
        return self.post_json(
            "/api/batch-workflows",
            {
                "preflight_id": str(preflight_id),
                "spec_hash": str(spec_hash),
                "idempotency_key": str(idempotency_key),
            },
            headers={"X-Hextile-Agent": "mcp"},
        )

    def list_batches(
        self,
        *,
        status: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Any:
        """GET /api/batch-workflows?status=&cursor=&limit=."""
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = int(limit)
        return self.get_json("/api/batch-workflows", params=params or None)

    def get_batch(self, job_id: str) -> Any:
        """GET /api/batch-workflows/{job_id}."""
        if not job_id:
            raise HextileClientError(
                "job_id is required", status_code=None, kind="other"
            )
        jid = urllib.parse.quote(str(job_id), safe="")
        return self.get_json(f"/api/batch-workflows/{jid}")

    def get_batch_items(
        self,
        job_id: str,
        *,
        outcome: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Any:
        """GET /api/batch-workflows/{job_id}/items?outcome=&cursor=&limit=."""
        if not job_id:
            raise HextileClientError(
                "job_id is required", status_code=None, kind="other"
            )
        jid = urllib.parse.quote(str(job_id), safe="")
        params: dict[str, Any] = {}
        if outcome:
            params["outcome"] = outcome
        if cursor:
            params["cursor"] = cursor
        if limit is not None:
            params["limit"] = int(limit)
        return self.get_json(
            f"/api/batch-workflows/{jid}/items",
            params=params or None,
        )

    def pause_batch(
        self, job_id: str, *, idempotency_key: str, expected_revision: int
    ) -> Any:
        """POST /api/batch-workflows/{job_id}/pause."""
        return self._batch_control(job_id, "pause", idempotency_key, expected_revision)

    def resume_batch(
        self, job_id: str, *, idempotency_key: str, expected_revision: int
    ) -> Any:
        """POST /api/batch-workflows/{job_id}/resume."""
        return self._batch_control(job_id, "resume", idempotency_key, expected_revision)

    def cancel_batch(
        self, job_id: str, *, idempotency_key: str, expected_revision: int
    ) -> Any:
        """POST /api/batch-workflows/{job_id}/cancel."""
        return self._batch_control(job_id, "cancel", idempotency_key, expected_revision)

    def retry_batch(
        self, job_id: str, *, idempotency_key: str, expected_revision: int
    ) -> Any:
        """POST /api/batch-workflows/{job_id}/retry-failed."""
        return self._batch_control(
            job_id, "retry-failed", idempotency_key, expected_revision
        )

    def import_batch_outputs(
        self,
        job_id: str,
        *,
        idempotency_key: str,
        expected_revision: int,
        scope: Optional[str] = None,
        item_ids: Optional[list[str]] = None,
    ) -> Any:
        """POST /api/batch-workflows/{job_id}/import — published outputs only."""
        if not job_id:
            raise HextileClientError(
                "job_id is required", status_code=None, kind="other"
            )
        if not idempotency_key:
            raise HextileClientError(
                "idempotency_key is required", status_code=None, kind="other"
            )
        body: dict[str, Any] = {
            "idempotency_key": str(idempotency_key),
            "expected_revision": int(expected_revision),
        }
        if item_ids is not None and scope is not None:
            raise HextileClientError(
                "import accepts either scope or item_ids",
                status_code=None,
                kind="other",
            )
        if item_ids is not None:
            if len(item_ids) > 500:
                raise HextileClientError(
                    "at most 500 item ids", status_code=None, kind="other"
                )
            body["item_ids"] = [str(i) for i in item_ids]
        else:
            body["scope"] = str(scope or "all_published")
        jid = urllib.parse.quote(str(job_id), safe="")
        return self.post_json(
            f"/api/batch-workflows/{jid}/import",
            body,
            headers={"X-Hextile-Agent": "mcp"},
        )

    def _batch_control(
        self,
        job_id: str,
        action: str,
        idempotency_key: str,
        expected_revision: int,
    ) -> Any:
        if not job_id:
            raise HextileClientError(
                "job_id is required", status_code=None, kind="other"
            )
        if not idempotency_key:
            raise HextileClientError(
                "idempotency_key is required", status_code=None, kind="other"
            )
        jid = urllib.parse.quote(str(job_id), safe="")
        return self.post_json(
            f"/api/batch-workflows/{jid}/{action}",
            {
                "idempotency_key": str(idempotency_key),
                "expected_revision": int(expected_revision),
            },
            headers={"X-Hextile-Agent": "mcp"},
        )

    # ── handshake (OPEN-3) ──────────────────────────────────────────────

    def probe(self) -> dict[str, Any]:
        """Reachability + workflows/run presence.

        Order:
          1. TCP/HTTP connect — refuse → app_down
          2. POST /api/workflows/run dry_run minimal body
             - 404 → upgrade
             - 422 → ok (handler present)
             - 2xx → ok
        """
        try:
            self.post_json(
                "/api/workflows/run",
                {
                    "dry_run": True,
                    # Intentionally incomplete so a live handler returns 422.
                    "workflow_id": None,
                    "document": None,
                },
            )
            return {"ok": True, "message": "360 Hextile reachable"}
        except HextileClientError as exc:
            if exc.kind == "app_down":
                return {"ok": False, "kind": "app_down", "message": str(exc)}
            if exc.kind == "upgrade" or exc.status_code == 404:
                return {"ok": False, "kind": "upgrade", "message": UPGRADE_MSG}
            if exc.status_code == 422:
                return {
                    "ok": True,
                    "message": "360 Hextile reachable (workflows/run present)",
                }
            # Other HTTP (402 license, 500, …) still means the app is up.
            return {
                "ok": True,
                "message": f"360 Hextile reachable (HTTP {exc.status_code})",
                "detail": str(exc),
            }

    # ── Fractal workshop and native sequences ──────────────────────────

    _FRACTAL_OP_FIELDS = {
        "set_base": ("target", "value"),
        "set_driver_mode": ("target", "mode"),
        "set_expression": ("target", "source", "refs"),
        "set_mapping": ("value",),
        "remove_mapping": ("id",),
        "remove_driver": ("target",),
        "upsert_modulator": ("value",),
        "remove_modulator": ("id",),
        "set_mouse_input": ("value",),
        "upsert_input_gate": ("value",),
        "remove_input_gate": ("id",),
        "upsert_input_binding": ("value",),
        "remove_input_binding": ("id",),
        "clock_action": ("value",),
        "set_timeline": ("value",),
        "set_fps": ("value",),
        "use_current_view_as_start": (),
        "resume_driver": ("target",),
    }
    _FRACTAL_KINDS = {"fractal_edit", "fractal_transport", "fractal_open", "fractal_save", "fractal_capture"}
    _FRACTAL_AGENT = {"X-Hextile-Agent": "mcp"}

    @staticmethod
    def _fractal_code(exc: HextileClientError) -> Optional[str]:
        try:
            payload = json.loads(exc.body or "")
        except (ValueError, TypeError):
            return None
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if isinstance(detail, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", detail):
            return detail
        if isinstance(detail, dict) and isinstance(detail.get("code"), str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", detail["code"]):
            return detail["code"]
        return None

    @staticmethod
    def _fractal_uncertain(exc: HextileClientError) -> bool:
        return exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500 or exc.status_code == 410 or 200 <= exc.status_code < 300

    def _fractal_forward(self, exc: HextileClientError) -> HextileClientError:
        code = self._fractal_code(exc)
        return HextileClientError(
            "Fractal action refused", status_code=exc.status_code, kind=exc.kind,
            receipt={"code": code} if code else None,
        )

    @staticmethod
    def _fractal_sha(value: Any) -> Optional[str]:
        if type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            return value
        return None

    @classmethod
    def _fractal_witness(cls, value: Any) -> dict[str, Any]:
        required = {
            "header_witness", "project_context_witness", "draft_generation",
            "source_generation", "viewer_generation", "renderer_generation", "owner_id",
        }
        if type(value) is not dict or not required <= set(value) <= required | {"scene_id", "scene_revision"}:
            raise HextileClientError("Invalid Fractal witness", kind="other", status_code=422)
        header = value["header_witness"]
        header_required = {"activationToken", "sessionId", "subjectKey"}
        if type(header) is not dict or not header_required <= set(header) <= header_required | {"projectId"}:
            raise HextileClientError("Invalid Fractal witness", kind="other", status_code=422)
        if any(type(header[key]) is not str or not header[key] for key in header_required):
            raise HextileClientError("Invalid Fractal witness", kind="other", status_code=422)
        if type(value["project_context_witness"]) is not str or not 1 <= len(value["project_context_witness"]) <= 256:
            raise HextileClientError("Invalid Fractal witness", kind="other", status_code=422)
        if type(value["owner_id"]) is not str or not 1 <= len(value["owner_id"]) <= 128:
            raise HextileClientError("Invalid Fractal witness", kind="other", status_code=422)
        for key in ("draft_generation", "source_generation", "viewer_generation", "renderer_generation"):
            if type(value[key]) is not int or value[key] < 0:
                raise HextileClientError("Invalid Fractal witness", kind="other", status_code=422)
        if "scene_id" in value and value["scene_id"] is not None and (type(value["scene_id"]) is not str or re.fullmatch(r"scn_[0-9a-f]{8}", value["scene_id"]) is None):
            raise HextileClientError("Invalid Fractal scene id", kind="other", status_code=422)
        if "scene_revision" in value and value["scene_revision"] is not None and cls._fractal_sha(value["scene_revision"]) is None:
            raise HextileClientError("Invalid Fractal scene revision", kind="other", status_code=422)
        return value

    @classmethod
    def _fractal_ops(cls, ops: Any) -> list[dict[str, Any]]:
        if type(ops) is not list or not 1 <= len(ops) <= 32:
            raise HextileClientError("Fractal edit batch must contain 1 to 32 ops", kind="other", status_code=422)
        for op in ops:
            fields = cls._FRACTAL_OP_FIELDS.get(op.get("op")) if type(op) is dict else None
            if fields is None or set(op) != {"op", *fields}:
                raise HextileClientError(
                    "Fractal edit op is not closed", kind="other", status_code=422,
                    receipt={"code": "invalid_animation"},
                )
            if "target" in op and (type(op["target"]) is not str or not op["target"]):
                raise HextileClientError("Invalid Fractal target", kind="other", status_code=422)
            if op["op"] == "set_mouse_input" and (
                type(op["value"]) is not dict or set(op["value"]) != {"schema", "enabled", "abi"}
                or op["value"].get("schema") != 1 or op["value"].get("abi") != "hx-mouse/1"
                or type(op["value"].get("enabled")) is not bool
            ):
                raise HextileClientError("Invalid Fractal mouse declaration", kind="other", status_code=422)
        return ops

    def _fractal_request_id(self, value: Any) -> str:
        if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None:
            raise HextileClientError("Invalid Fractal client_request_id", kind="other", status_code=422)
        return value

    def _post_fractal_action(self, kind: str, args: Mapping[str, Any]) -> dict[str, Any]:
        request_id = self._fractal_request_id(args.get("client_request_id") if isinstance(args, Mapping) else None)
        witness = self._fractal_witness(args.get("witness") if isinstance(args, Mapping) else None)
        body: dict[str, Any] = {"kind": kind, "client_request_id": request_id, "witness": witness}
        if kind == "fractal_edit":
            if set(args) != {"client_request_id", "witness", "expected_draft_generation", "ops"}:
                raise HextileClientError("Fractal edit arguments are not closed", kind="other", status_code=422)
            if args["expected_draft_generation"] != witness["draft_generation"] or type(args["expected_draft_generation"]) is not int:
                raise HextileClientError("Fractal edit generation does not match the witness", kind="other", status_code=422)
            body["expected_draft_generation"] = args["expected_draft_generation"]
            body["ops"] = self._fractal_ops(args["ops"])
        elif kind == "fractal_transport":
            action = args.get("action")
            allowed = {"client_request_id", "witness", "action"}
            if action == "seek":
                allowed.add("time")
            elif action == "step":
                allowed.add("frames")
            elif action not in {"play", "pause", "rewind"}:
                raise HextileClientError("Invalid Fractal transport action", kind="other", status_code=422)
            if set(args) != allowed:
                raise HextileClientError("Fractal transport arguments are not closed", kind="other", status_code=422)
            body["action"] = action
            if action == "seek":
                body["time"] = args["time"]
            if action == "step":
                body["frames"] = args["frames"]
        elif kind == "fractal_open":
            if set(args) != {"client_request_id", "witness", "scene_id"} or re.fullmatch(r"scn_[0-9a-f]{8}", str(args.get("scene_id"))) is None:
                raise HextileClientError("Fractal open arguments are not closed", kind="other", status_code=422)
            body["scene_id"] = args["scene_id"]
        elif kind == "fractal_capture":
            if set(args) != {"client_request_id", "witness"}:
                raise HextileClientError("Fractal capture takes only its original request and witness", kind="other", status_code=422)
            self._require_native_render(fractal_still_capture=True)
        else:
            allowed = {"client_request_id", "witness", "mode", "target_scene_id"}
            if not isinstance(args, Mapping) or not allowed <= set(args) <= allowed | {"name", "scene_revision"}:
                raise HextileClientError("Fractal save arguments are not closed", kind="other", status_code=422)
            if args["mode"] not in {"save", "save_as"} or re.fullmatch(r"scn_[0-9a-f]{8}", str(args.get("target_scene_id"))) is None:
                raise HextileClientError("Invalid Fractal save target", kind="other", status_code=422)
            if args["mode"] == "save" and self._fractal_sha(args.get("scene_revision")) is None:
                raise HextileClientError("Save requires the adopted scene revision", kind="other", status_code=422)
            if args["mode"] == "save_as" and "scene_revision" in args:
                raise HextileClientError("Save As is create-only and takes no scene revision", kind="other", status_code=422)
            body["mode"] = args["mode"]
            body["target_scene_id"] = args["target_scene_id"]
            if "name" in args:
                body["name"] = args["name"]
            if "scene_revision" in args:
                body["scene_revision"] = args["scene_revision"]
        try:
            data = self.post_json("/api/agent/fractal-actions", body, headers=self._FRACTAL_AGENT)
        except HextileClientError as exc:
            if kind == "fractal_save" and self._fractal_uncertain(exc):
                return self._reconcile_fractal_save(args)
            if self._fractal_uncertain(exc):
                raise HextileClientError(
                    "Fractal action outcome unknown. Read get_fractal_request for this client_request_id. Unknown is not expiry or refusal.",
                    status_code=exc.status_code, kind="fractal_outcome_unknown",
                    receipt={"client_request_id": request_id, "status": "unknown"},
                ) from exc
            raise self._fractal_forward(exc) from exc
        except Exception as exc:
            if kind == "fractal_save":
                return self._reconcile_fractal_save(args)
            raise HextileClientError(
                "Fractal action outcome unknown. Read get_fractal_request for this client_request_id.",
                kind="fractal_outcome_unknown", receipt={"client_request_id": request_id, "status": "unknown"},
            ) from exc
        return self._fractal_action_receipt(data, request_id)

    def _reconcile_fractal_save(self, args: Mapping[str, Any]) -> dict[str, Any]:
        request_id = str(args["client_request_id"])
        target = str(args["target_scene_id"])
        try:
            data = self.get_json(
                f"/api/agent/fractal-actions/requests/{urllib.parse.quote(request_id, safe='')}",
                headers=self._FRACTAL_AGENT,
            )
            receipt = self._fractal_action_receipt(data, request_id)
            if receipt.get("status") != "unknown" or receipt.get("result"):
                return receipt
        except HextileClientError:
            pass
        try:
            written = self.get_json(
                f"/api/fractal/scenes/{urllib.parse.quote(target, safe='')}/write-status/{urllib.parse.quote(request_id, safe='')}"
            )
        except HextileClientError as exc:
            raise HextileClientError(
                "Fractal Save outcome unknown. Unknown is not expiry and is not a reason to post again.",
                status_code=exc.status_code, kind="fractal_outcome_unknown",
                receipt={"client_request_id": request_id, "status": "unknown", "scene_id": target},
            ) from exc
        revision = self._fractal_sha(written.get("revision") if isinstance(written, dict) else None)
        if isinstance(written, dict) and written.get("status") == "accepted" and revision:
            return {
                "client_request_id": request_id, "status": "applied", "kind": "fractal_save",
                "result": {"scene_id": target, "client_request_id": request_id, "scene_revision": revision},
            }
        raise HextileClientError(
            "Fractal Save outcome unknown. Unknown is not expiry and is not a reason to post again.",
            kind="fractal_outcome_unknown",
            receipt={"client_request_id": request_id, "status": "unknown", "scene_id": target},
        )

    def _fractal_action_receipt(self, data: Any, request_id: str) -> dict[str, Any]:
        if not isinstance(data, dict) or data.get("status") not in {"pending", "applied", "refused", "unknown"}:
            raise HextileClientError("Fractal action acknowledgement unknown. Read the original request id; do not repost.",
                                     kind="fractal_outcome_unknown", status_code=200,
                                     receipt={"client_request_id": request_id, "status": "unknown"})
        receipt: dict[str, Any] = {"client_request_id": request_id, "status": data["status"]}
        if type(data.get("ok")) is bool:
            receipt["ok"] = data["ok"]
        if type(data.get("ticket_id")) is str:
            receipt["ticket_id"] = data["ticket_id"]
        if data.get("kind") in self._FRACTAL_KINDS:
            receipt["kind"] = data["kind"]
        if type(data.get("reason")) is str:
            receipt["reason"] = data["reason"]
        body = data.get("result")
        if data.get("kind") == "fractal_capture" and data["status"] == "applied" and not isinstance(body, dict):
            raise HextileClientError("Known Fractal mint ID missing; recover the original request", kind="fractal_outcome_unknown",
                                     receipt={"client_request_id": request_id, "status": "unknown"})
        if isinstance(body, dict):
            if data.get("kind") == "fractal_capture":
                receipt["result"] = self._fractal_capture_result(body, minted=data["status"] == "applied")
                return receipt
            projected: dict[str, Any] = {}
            if type(body.get("scene_id")) is str:
                projected["scene_id"] = body["scene_id"]
            if type(body.get("client_request_id")) is str:
                projected["client_request_id"] = body["client_request_id"]
            for key in ("scene_revision", "base_scene_revision"):
                revision = self._fractal_sha(body.get(key))
                if revision:
                    projected[key] = revision
            if projected:
                receipt["result"] = projected
        return receipt

    @classmethod
    def _fractal_capture_result(cls, body: dict[str, Any], *, minted: bool) -> dict[str, Any]:
        fields = {"scene_id", "scene_revision", "time", "sample_id", "width", "height"}
        if minted:
            fields |= {"render_id", "node_id"}
        sample, time = body.get("sample_id"), body.get("time")
        static = body.get("static_frame")
        if static is not None:
            if (set(body) != fields | {"static_frame"} or sample is not None or time is not None
                    or type(static) is not dict
                    or set(static) != {"generation", "context_generation", "capture_retirement", "width", "height"}
                    or any(type(static[key]) is not int or static[key] < 0 for key in
                           ("generation", "context_generation", "capture_retirement"))
                    or any(type(static[key]) is not int or not 1 <= static[key] <= limit
                           for key, limit in (("width", 2048), ("height", 1024)))
                    or any(type(body[key]) is not int or not 1 <= body[key] <= static[key]
                           for key in ("width", "height"))):
                raise HextileClientError("Invalid bounded Fractal static capture receipt", kind="fractal_outcome_unknown",
                                         receipt={"status": "unknown"})
        elif (set(body) != fields or type(time) is not dict or set(time) != {"num", "den"}
                or any(type(time[key]) is not str or re.fullmatch(
                    r"-?[0-9]{1,32}" if key == "num" else r"[1-9][0-9]{0,31}", time[key]) is None
                    for key in ("num", "den"))
                or type(sample) is not dict or set(sample) != {"owner_generation", "source_generation",
                    "evaluation_sequence", "exact_time", "document_hash"}
                or any(type(sample[key]) is not int or sample[key] < 0 for key in
                       ("owner_generation", "source_generation", "evaluation_sequence"))
                or sample["exact_time"] != time or cls._fractal_sha(sample["document_hash"]) is None
                or any(type(body[key]) is not int or not 1 <= body[key] <= limit
                       for key, limit in (("width", 2048), ("height", 1024)))):
            raise HextileClientError("Invalid bounded Fractal capture receipt", kind="fractal_outcome_unknown",
                                     receipt={"status": "unknown"})
        if (body["scene_id"] is not None and re.fullmatch(r"scn_[0-9a-f]{8}", str(body["scene_id"])) is None
                or body["scene_revision"] is not None and cls._fractal_sha(body["scene_revision"]) is None
                or minted and any(type(body[key]) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", body[key]) is None
                                  for key in ("render_id", "node_id"))):
            raise HextileClientError("Invalid bounded Fractal capture receipt", kind="fractal_outcome_unknown",
                                     receipt={"status": "unknown"})
        return dict(body)

    def get_fractal_context(self) -> dict[str, Any]:
        data = self.get_json("/api/agent/live-context", params={"include_nav": 0, "include_active_tool": 0})
        surface = data.get("current_surface") if isinstance(data, dict) else None
        if not isinstance(surface, dict) or surface.get("kind") != "fractal_workshop":
            raise HextileClientError(
                "Fractal workshop is not mounted.", status_code=503, kind="http",
                receipt={"code": "fractal_unavailable"},
            )
        result = self._fractal_inspect(surface)
        try:
            result["witness"] = self._fractal_witness({key: surface[key] for key in (
                "header_witness", "project_context_witness", "scene_id", "scene_revision",
                "draft_generation", "source_generation", "viewer_generation", "renderer_generation", "owner_id",
            ) if key in surface and surface[key] is not None})
        except HextileClientError:
            pass  # An incomplete observation has no current document/renderer witness.
        return result

    @classmethod
    def _fractal_inspect(cls, surface: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if type(surface.get("scene_id")) is str and re.fullmatch(r"scn_[0-9a-f]{8}", surface["scene_id"]):
            out["scene_id"] = surface["scene_id"]
        revision = cls._fractal_sha(surface.get("scene_revision"))
        if revision:
            out["scene_revision"] = revision
        for key in ("draft_generation", "source_generation", "viewer_generation", "renderer_generation"):
            if type(surface.get(key)) is int and surface[key] >= 0:
                out[key] = surface[key]
        for key in ("owner_id", "project_context_witness"):
            if type(surface.get(key)) is str and surface[key] and not cls._fractal_secret(surface[key]):
                out[key] = surface[key]
        targets = [item for item in surface.get("registry_targets", [])
                   if type(item) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", item)][:1024] if isinstance(surface.get("registry_targets"), list) else []
        if targets:
            out["registry_targets"] = targets
        orphans = cls._fractal_pairs(surface.get("retained_orphans"))
        if orphans:
            out["retained_orphans"] = orphans
        if isinstance(surface.get("capabilities"), list):
            tokens = [item for item in surface["capabilities"] if type(item) is str and re.fullmatch(r"[A-Za-z0-9_./+-]{1,64}", item)][:32]
            if tokens:
                out["capabilities"] = tokens
        suspensions = cls._fractal_pairs(surface.get("suspensions"))
        if suspensions:
            out["suspensions"] = suspensions
        if isinstance(surface.get("diagnostics"), list):
            rows = []
            for item in surface["diagnostics"][:32]:
                if not isinstance(item, dict):
                    continue
                row = {}
                if type(item.get("code")) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", item["code"]):
                    row["code"] = item["code"]
                if type(item.get("target")) is str and item["target"]:
                    row["target"] = item["target"]
                if row:
                    rows.append(row)
            if rows:
                out["diagnostics"] = rows
        for key in ("base", "effective"):
            numbers = surface.get(key)
            if isinstance(numbers, dict):
                admitted = set(targets)
                projected = {
                    name: value for name, value in numbers.items()
                    if name in admitted and type(value) in (int, float) and math.isfinite(value)
                }
                if projected:
                    out[key] = projected
        return out

    @staticmethod
    def _fractal_secret(value: str) -> bool:
        return value.startswith("/") or "\\" in value or (len(value) >= 3 and value[1] == ":")

    @classmethod
    def _fractal_pairs(cls, value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        rows = []
        for item in value[:32]:
            if not isinstance(item, dict):
                continue
            target, reason = item.get("target"), item.get("reason")
            if type(target) is str and target and type(reason) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason):
                rows.append({"target": target, "reason": reason})
        return rows

    def apply_fractal_edits(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self._post_fractal_action("fractal_edit", args)

    def control_fractal_timeline(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self._post_fractal_action("fractal_transport", args)

    def open_fractal_scene(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self._post_fractal_action("fractal_open", args)

    def save_fractal_scene(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self._post_fractal_action("fractal_save", args)

    def capture_fractal_still(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self._post_fractal_action("fractal_capture", args)

    def get_fractal_request(self, client_request_id: str) -> dict[str, Any]:
        request_id = self._fractal_request_id(client_request_id)
        try:
            data = self.get_json(
                f"/api/agent/fractal-actions/requests/{urllib.parse.quote(request_id, safe='')}",
                headers=self._FRACTAL_AGENT,
            )
        except HextileClientError as exc:
            if exc.status_code == 410:
                raise HextileClientError(
                    "Fractal request outcome unknown. Expiry is not refusal or permission to repeat a capture or Save.",
                    status_code=410, kind="fractal_outcome_unknown",
                    receipt={"client_request_id": request_id, "status": "unknown"},
                ) from exc
            raise
        return self._fractal_action_receipt(data, request_id)

    def _fractal_sequence_body(self, body: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "scene_id", "scene_revision", "idempotency_key", "name", "frame_rate",
            "start_time", "end_time", "frame_count", "seed", "quality", "width", "height",
            "output", "publication_mode",
        }
        optional = {"destination_intent", "project_path", "folder_export"}
        if (not isinstance(body, Mapping) or not required <= set(body) <= required | optional
                or body.get("publication_mode") != "deferred"
                or body.get("folder_export") is not None
                or ("destination_intent" in body and body["destination_intent"] is not None
                    and not _native_folder_intent(body["destination_intent"]))
                or ("project_path" in body and body["project_path"] is not None
                    and not _absolute_task_path(body["project_path"]))):
            raise HextileClientError("Expected a closed deferred Fractal sequence request", kind="other", status_code=422)
        if self._fractal_sha(body.get("scene_revision")) is None or re.fullmatch(r"scn_[0-9a-f]{8}", str(body.get("scene_id"))) is None:
            raise HextileClientError("Invalid saved Fractal scene identity", kind="other", status_code=422)
        if (type(body.get("idempotency_key")) is not str or not 1 <= len(body["idempotency_key"]) <= 128
                or type(body.get("name")) is not str or not 1 <= len(body["name"]) <= 128
                or body.get("quality") not in {"explore_smoke", "final_8k"}
                or type(body.get("seed")) is not int or not 0 <= body["seed"] < 2**32):
            raise HextileClientError("Invalid Fractal sequence choices", kind="other", status_code=422)
        try:
            rate = body["frame_rate"]
            if type(rate) is not dict or set(rate) != {"num", "den"} or any(type(rate[k]) is not int or not 1 <= rate[k] <= 1000000 for k in rate):
                raise ValueError()
            fps = Fraction(rate["num"], rate["den"])
            if not 1 <= fps <= 120 or fps.denominator != rate["den"]:
                raise ValueError()
            times = []
            for key in ("start_time", "end_time"):
                value = body[key]
                if type(value) is not dict or set(value) != {"num", "den"} or any(type(value[k]) is not str for k in value):
                    raise ValueError()
                if not re.fullmatch(r"(0|[1-9][0-9]{0,31})", value["num"]) or not re.fullmatch(r"[1-9][0-9]{0,31}", value["den"]):
                    raise ValueError()
                exact = Fraction(int(value["num"]), int(value["den"]))
                if exact.numerator != int(value["num"]) or exact.denominator != int(value["den"]):
                    raise ValueError()
                times.append(exact)
            samples = (times[1] - times[0]) * fps
            if not 0 <= times[0] < times[1] <= 86400 or type(body["frame_count"]) is not int or not 1 <= body["frame_count"] <= 10000 or body["frame_count"] != -(-samples.numerator // samples.denominator):
                raise ValueError()
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            raise HextileClientError("Invalid exact Fractal sequence range or rational FPS", kind="other", status_code=422) from exc
        output = body["output"]
        width, height = body["width"], body["height"]
        if type(width) is not int or type(height) is not int or not isinstance(output, dict):
            raise HextileClientError("Invalid Fractal sequence geometry", kind="other", status_code=422, receipt={"code": "geometry"})
        projection = output.get("projection")
        if projection == "equirectangular":
            if (set(output) != {"projection", "pan", "tilt", "roll"}
                    or any(type(output[key]) not in (int, float) or output[key] != 0
                           for key in ("pan", "tilt", "roll"))
                    or not (64 <= height <= 8192 and 128 <= width <= 16384 and height % 2 == 0 and width == 2 * height)):
                raise HextileClientError(
                    "Fractal equirectangular output requires exact 2:1 and at least 128x64",
                    kind="other", status_code=422, receipt={"code": "geometry"},
                )
        elif projection in {"fulldome", "fulldome_angular"}:
            if (set(output) != {"projection", "diameter", "fov_deg", "pan", "tilt", "roll"}
                    or type(output["diameter"]) is not int
                    or output["diameter"] not in {1024, 2048, 4096, 8192}
                    or width != height or width != output["diameter"]
                    or any(type(output[key]) not in (int, float) or not math.isfinite(output[key])
                           or not lo <= output[key] <= hi for key, lo, hi in
                           (("fov_deg", 10, 360), ("pan", -180, 180), ("tilt", -90, 90), ("roll", -180, 180)))):
                raise HextileClientError(
                    "Fractal Dome output must be square at diameter 1024, 2048, 4096, or 8192",
                    kind="other", status_code=422, receipt={"code": "geometry"},
                )
        else:
            raise HextileClientError("Invalid Fractal sequence projection", kind="other", status_code=422, receipt={"code": "geometry"})
        return dict(body)

    def _fractal_sequence_error(self, exc: HextileClientError, *, uncertain: bool) -> HextileClientError:
        code = self._fractal_code(exc)
        if uncertain and self._fractal_uncertain(exc):
            return HextileClientError(
                "Fractal sequence POST outcome unknown. GET the acknowledged sequence id and compare request_hash. Do not mint another id.",
                status_code=exc.status_code, kind="fractal_sequence_outcome_unknown",
                receipt={"status": "unknown"},
            )
        return HextileClientError(
            "Fractal sequence refused", status_code=exc.status_code, kind=exc.kind,
            receipt={"code": code} if code else None,
        )

    @staticmethod
    def _fractal_sequence_identity(body: Mapping[str, Any]) -> dict[str, str]:
        # Match APP's backwards-compatible request hash defaults, not a guessed locator.
        request = {**body, "folder_export": None}
        if request.get("destination_intent") is None:
            request.pop("destination_intent", None)
        else:
            request["destination_intent"] = {**request["destination_intent"],
                                             "quality_if_jpg": request["destination_intent"].get("quality_if_jpg")}
        output = body["output"]
        if output["projection"] in {"fulldome", "fulldome_angular"}:
            normalized = dict(output)
            for key in ("fov_deg", "pan", "tilt", "roll"):
                if key in normalized:
                    value = float(normalized[key])
                    normalized[key] = 0.0 if key != "fov_deg" and value == 0 else value
            request["output"] = normalized
        else:
            request["output"] = {**output, "pan": 0, "tilt": 0, "roll": 0}
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        identity = f"fractal-sequence/1\0{body['scene_id']}\0{body['idempotency_key']}".encode()
        return {"sequence_id": "seq_" + hashlib.sha256(identity).hexdigest()[:32],
                "request_hash": "sha256:" + hashlib.sha256(encoded).hexdigest()}

    def _fractal_sequence_post(self, body: Mapping[str, Any], *, preflight: bool) -> dict[str, Any]:
        checked = self._fractal_sequence_body(body)
        if checked.get("destination_intent") is not None or "project_path" in checked:
            self._require_native_render()
        path = "/api/fractal/sequences/preflight" if preflight else "/api/fractal/sequences"
        try:
            data = self.post_json(path, checked)
        except HextileClientError as exc:
            error = self._fractal_sequence_error(exc, uncertain=not preflight)
            if error.kind == "fractal_sequence_outcome_unknown":
                error.receipt.update(self._fractal_sequence_identity(checked))
            raise error from exc
        except Exception as exc:
            safe = HextileClientError("Fractal sequence transport failed", kind="app_down")
            error = self._fractal_sequence_error(safe, uncertain=not preflight)
            if error.kind == "fractal_sequence_outcome_unknown":
                error.receipt.update(self._fractal_sequence_identity(checked))
            raise error from exc
        if preflight:
            keys = ("frame_count", "source_width", "source_height", "output_width", "output_height")
            if not isinstance(data, dict) or any(type(data.get(key)) is not int or data[key] < 0 for key in keys) or self._fractal_sha(data.get("render_identity")) is None:
                raise HextileClientError("Invalid Fractal sequence preflight receipt", kind="other")
            return {key: data[key] for key in (*keys, "render_identity")}
        known = self._fractal_sequence_identity(checked)
        if (not isinstance(data, dict) or data.get("sequence_id") != known["sequence_id"]
                or data.get("request_hash") != known["request_hash"]
                or data.get("status") not in {"queued", "processing", "completed", "completed_with_errors",
                                               "failed", "cancelled", "incomplete", "paused", "stopped"}):
            raise HextileClientError("Fractal sequence acknowledgement unknown. Read the known sequence id; do not repost.",
                                     kind="fractal_sequence_outcome_unknown",
                                     receipt={"status": "unknown", **known})
        receipt = dict(known)
        receipt["status"] = data["status"]
        for key in ("recipe_hash",):
            if self._fractal_sha(data.get(key)):
                receipt[key] = data[key]
        return receipt

    def preflight_fractal_sequence(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._fractal_sequence_post(body, preflight=True)

    def inspect_fractal_sequence_output(self, args: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(args, Mapping) or set(args) != {"request", "destination"}:
            raise HextileClientError("Expected a closed Fractal destination inspection", kind="other", status_code=422)
        request = self._fractal_sequence_body(args["request"])
        destination = args["destination"]
        if (not _native_folder_intent(destination)
                or (request.get("destination_intent") is not None
                    and not _same_native_intent(request["destination_intent"], destination))):
            raise HextileClientError("Inspection destination differs from the retained Fractal intent", kind="other", status_code=422)
        self._require_native_render()
        try:
            data = self.post_json("/api/fractal/sequences/inspect", {"request": request, "destination": dict(destination)},
                                  timeout=LONG_OPERATION_TIMEOUT_S)
            return _native_inspection_result(data, "fractal")
        except HextileClientError as exc:
            raise self._fractal_sequence_error(exc, uncertain=False) from exc

    def render_fractal_sequence(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._fractal_sequence_post(body, preflight=False)

    def get_fractal_sequence(self, sequence_id: str) -> dict[str, Any]:
        if type(sequence_id) is not str or re.fullmatch(r"seq_[0-9a-f]{32}", sequence_id) is None:
            raise HextileClientError("Expected a known Fractal sequence id", kind="other", status_code=422)
        try:
            data = self.get_json(f"/api/fractal/sequences/{sequence_id}")
        except HextileClientError as exc:
            if exc.status_code == 404:
                raise HextileClientError(
                    "Known Fractal sequence id is absent. An uncertain render POST remains unknown. Do not mint another id.",
                    status_code=404, kind="fractal_sequence_outcome_unknown",
                    receipt={"sequence_id": sequence_id, "status": "unknown"},
                ) from exc
            raise self._fractal_sequence_error(exc, uncertain=False) from exc
        if not isinstance(data, dict) or data.get("sequence_id") != sequence_id:
            raise HextileClientError("Invalid Fractal sequence status", kind="other")
        receipt: dict[str, Any] = {"sequence_id": sequence_id}
        if data.get("status") in {"queued", "processing", "completed", "completed_with_errors",
                                  "failed", "cancelled", "incomplete", "paused", "stopped"}:
            receipt["status"] = data["status"]
        for key in ("request_hash", "recipe_hash", "render_identity"):
            if self._fractal_sha(data.get(key)):
                receipt[key] = data[key]
        for key in ("source_width", "source_height", "output_width", "output_height", "frame_count", "width", "height"):
            if type(data.get(key)) is int and data[key] >= 0:
                receipt[key] = data[key]
        for key in ("published_cursor", "frames_pending", "frames_queued", "frames_processing",
                    "frames_completed", "frames_failed", "current_frame_index", "attempt_revision"):
            if type(data.get(key)) is int and data[key] >= 0:
                receipt[key] = data[key]
        if type(data.get("attempt_id")) is str and re.fullmatch(r"attempt_[0-9a-f]{32}", data["attempt_id"]):
            receipt["attempt_id"] = data["attempt_id"]
        for key in ("frame_rate", "start_time", "end_time"):
            value = data.get(key)
            if isinstance(value, dict) and set(value) == {"num", "den"}:
                if key == "frame_rate" and all(type(value[k]) is int and value[k] > 0 for k in value):
                    receipt[key] = dict(value)
                elif key != "frame_rate" and all(type(value[k]) is str and re.fullmatch(r"[0-9]{1,32}", value[k]) for k in value) and int(value["den"]) > 0:
                    receipt[key] = dict(value)
        attempt = self._fractal_attempt(data.get("folder_export"))
        if attempt:
            receipt["folder_export"] = attempt
        if isinstance(data.get("publication_attempts"), list):
            receipt["publication_attempts"] = [row for raw in data["publication_attempts"][:8]
                                               if (row := self._fractal_attempt(raw))]
        output = data.get("output")
        if isinstance(output, dict) and output.get("projection") in {"equirectangular", "fulldome", "fulldome_angular"}:
            projected = {"projection": output["projection"]}
            for key in ("diameter", "fov_deg", "pan", "tilt", "roll"):
                value = output.get(key)
                if type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(value):
                    projected[key] = value
            receipt["output"] = projected
        receipt.update(_native_sequence_fields(data))
        destination = data.get("destination_intent")
        if _native_folder_intent(destination):
            receipt["destination_intent"] = {"format": destination["format"],
                                             "quality_if_jpg": destination.get("quality_if_jpg")}
        return receipt

    @classmethod
    def _fractal_attempt(cls, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict) or type(data.get("attempt_id")) is not str or not re.fullmatch(r"attempt_[0-9a-f]{32}", data["attempt_id"]):
            return {}
        out = {"attempt_id": data["attempt_id"]}
        for key in ("attempt_revision", "frames_completed", "frames_failed", "quality_if_jpg"):
            if type(data.get(key)) is int and data[key] >= 0:
                out[key] = data[key]
        for key in ("status", "reason", "format"):
            if type(data.get(key)) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", data[key]):
                out[key] = data[key]
        if cls._fractal_sha(data.get("transaction_fingerprint")):
            out["transaction_fingerprint"] = data["transaction_fingerprint"]
        if type(data.get("destination_available")) is bool:
            out["destination_available"] = data["destination_available"]
        observation = _native_observation(data.get("observation"))
        if observation is not None:
            out["observation"] = observation
        return out

    def _fractal_export_args(self, args: Mapping[str, Any], *, submit: bool) -> tuple[str, dict[str, Any]]:
        required = {"sequence_id", "destination_folder", "format"}
        if submit:
            required.add("transaction_fingerprint")
        if not isinstance(args, Mapping) or not required <= set(args) <= required | {"quality_if_jpg"}:
            raise HextileClientError("Expected a closed Fractal folder export", kind="other", status_code=422)
        sequence_id = args["sequence_id"]
        if type(sequence_id) is not str or re.fullmatch(r"seq_[0-9a-f]{32}", sequence_id) is None:
            raise HextileClientError("Expected a known Fractal sequence id", kind="other", status_code=422)
        encoding = args["format"]
        quality = args.get("quality_if_jpg")
        if encoding not in {"PNG", "JPG"} or (encoding == "JPG") != (type(quality) is int and 1 <= quality <= 100):
            raise HextileClientError("Invalid Fractal folder encoding", kind="other", status_code=422)
        if encoding == "PNG" and "quality_if_jpg" in args:
            raise HextileClientError("PNG export omits quality_if_jpg", kind="other", status_code=422)
        body = {"destination_folder": args["destination_folder"], "format": encoding}
        if quality is not None:
            body["quality_if_jpg"] = quality
        if submit:
            if self._fractal_sha(args.get("transaction_fingerprint")) is None:
                raise HextileClientError("Export requires the preflight transaction_fingerprint", kind="other", status_code=422)
            body["transaction_fingerprint"] = args["transaction_fingerprint"]
        return sequence_id, body

    def _fractal_export_receipt(self, data: Any, sequence_id: str) -> dict[str, Any]:
        if not isinstance(data, dict) or data.get("sequence_id") != sequence_id or self._fractal_sha(data.get("transaction_fingerprint")) is None:
            raise HextileClientError("Fractal export acknowledgement unknown. Read the known sequence and attempt; do not repost.",
                                     kind="fractal_sequence_outcome_unknown",
                                     receipt={"sequence_id": sequence_id, "status": "unknown"})
        receipt = {
            "sequence_id": sequence_id,
            "transaction_fingerprint": data["transaction_fingerprint"],
        }
        if type(data.get("attempt_id")) is str and re.fullmatch(r"attempt_[0-9a-f]{32}", data["attempt_id"]):
            receipt["attempt_id"] = data["attempt_id"]
        if type(data.get("status")) is str:
            receipt["status"] = data["status"]
        if type(data.get("attempt_revision")) is int and data["attempt_revision"] >= 0:
            receipt["attempt_revision"] = data["attempt_revision"]
        if self._fractal_sha(data.get("recipe_hash")):
            receipt["recipe_hash"] = data["recipe_hash"]
        return receipt

    def preflight_fractal_sequence_export(self, args: Mapping[str, Any]) -> dict[str, Any]:
        sequence_id, body = self._fractal_export_args(args, submit=False)
        try:
            data = self.post_json(f"/api/fractal/sequences/{sequence_id}/export/preflight", body)
        except HextileClientError as exc:
            raise self._fractal_sequence_error(exc, uncertain=False) from exc
        return self._fractal_export_receipt(data, sequence_id)

    def export_fractal_sequence(self, args: Mapping[str, Any]) -> dict[str, Any]:
        sequence_id, body = self._fractal_export_args(args, submit=True)
        try:
            data = self.post_json(f"/api/fractal/sequences/{sequence_id}/export", body)
        except HextileClientError as exc:
            if self._fractal_uncertain(exc):
                raise HextileClientError(
                    "Fractal export POST outcome unknown. GET the known sequence and attempt. Do not post again.",
                    status_code=exc.status_code, kind="fractal_sequence_outcome_unknown",
                    receipt={"status": "unknown", "sequence_id": sequence_id},
                ) from exc
            raise self._fractal_sequence_error(exc, uncertain=False) from exc
        except Exception as exc:
            raise HextileClientError("Fractal export outcome unknown. Read the known sequence; do not repost.",
                                     kind="fractal_sequence_outcome_unknown",
                                     receipt={"sequence_id": sequence_id, "status": "unknown"}) from exc
        receipt = self._fractal_export_receipt(data, sequence_id)
        if receipt["transaction_fingerprint"] != body["transaction_fingerprint"]:
            raise HextileClientError("Invalid Fractal export acknowledgement", kind="other")
        return receipt

    def control_fractal_sequence(self, args: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(args, Mapping) or "sequence_id" not in args or "action" not in args:
            raise HextileClientError("Expected closed Fractal sequence control", kind="other", status_code=422)
        sequence_id, action = args["sequence_id"], args["action"]
        if (type(sequence_id) is not str or re.fullmatch(r"seq_[0-9a-f]{32}", sequence_id) is None
                or type(action) is not str):
            raise HextileClientError("Expected a known Fractal sequence id", kind="other", status_code=422)
        publication = action in {"cancel_export", "retry_export", "open_folder"}
        if action == "stop" and set(args) == {"sequence_id", "action", "run_id"}:
            if type(args["run_id"]) is not str or re.fullmatch(r"[0-9a-f]{32}", args["run_id"]) is None:
                raise HextileClientError("Stop requires the observed Fractal run_id", kind="other", status_code=422)
            suffix, body = "stop", {"run_id": args["run_id"]}
        elif action == "resume" and set(args) == {"sequence_id", "action"}:
            suffix, body = "resume", None
        elif action == "continue" and set(args) == {"sequence_id", "action", "request", "destination", "inspection_fingerprint"}:
            request = self._fractal_sequence_body(args["request"])
            destination = args["destination"]
            if (not _native_folder_intent(destination)
                    or request.get("destination_intent") is not None
                    and not _same_native_intent(request["destination_intent"], destination)
                    or self._fractal_sha(args["inspection_fingerprint"]) is None):
                raise HextileClientError("Continue requires the exact inspected Fractal intent", kind="other", status_code=422)
            self._require_native_render()
            suffix, body = "continue", {"request": request, "destination": dict(destination),
                                        "inspection_fingerprint": args["inspection_fingerprint"]}
        elif publication:
            if set(args) != {"sequence_id", "action", "attempt_id", "attempt_revision"}:
                raise HextileClientError("Publication control requires the observed attempt id and revision", kind="other", status_code=422)
            if (type(args["attempt_id"]) is not str or re.fullmatch(r"attempt_[0-9a-f]{32}", args["attempt_id"]) is None
                    or type(args["attempt_revision"]) is not int or args["attempt_revision"] < 0):
                raise HextileClientError("Invalid Fractal export attempt", kind="other", status_code=422)
            suffix = {"cancel_export": "export/cancel", "retry_export": "export/retry", "open_folder": "export/open-folder"}[action]
            body = {"attempt_id": args["attempt_id"], "attempt_revision": args["attempt_revision"]}
        else:
            raise HextileClientError("Invalid Fractal sequence control", kind="other", status_code=422)
        try:
            data = self.post_json(f"/api/fractal/sequences/{sequence_id}/{suffix}", body,
                                  timeout=LONG_OPERATION_TIMEOUT_S if action == "continue" else None)
        except HextileClientError as exc:
            if self._fractal_uncertain(exc):
                raise HextileClientError(
                    "Fractal control POST outcome unknown. GET the known sequence before another action.",
                    status_code=exc.status_code, kind="fractal_sequence_outcome_unknown",
                    receipt={"status": "unknown", "sequence_id": sequence_id,
                             **({"inspection_fingerprint": args["inspection_fingerprint"],
                                 "idempotency_key": args["request"]["idempotency_key"]} if action == "continue" else {})},
                ) from exc
            if exc.status_code == 409 and self._fractal_code(exc) == "sequence_run_changed":
                raise HextileClientError("Native Fractal run changed. GET fresh status; never retry Stop without its observed run_id.",
                                         status_code=409, kind="http", receipt={"sequence_id": sequence_id,
                                                                                "code": "sequence_run_changed"}) from exc
            raise self._fractal_sequence_error(exc, uncertain=False) from exc
        if not isinstance(data, dict) or data.get("sequence_id") != sequence_id:
            raise HextileClientError("Fractal control acknowledgement unknown; GET the known sequence",
                                     kind="fractal_sequence_outcome_unknown", status_code=202,
                                     receipt={"sequence_id": sequence_id, "status": "unknown"})
        receipt = {"sequence_id": sequence_id, "action": action}
        if action in {"stop", "resume", "continue"} and data.get("status") not in {
                "queued", "processing", "completed", "completed_with_errors",
                "failed", "cancelled", "incomplete", "paused", "stopped"}:
            raise HextileClientError("Fractal control acknowledgement unknown; GET the known sequence",
                                     kind="fractal_sequence_outcome_unknown", status_code=202,
                                     receipt={"sequence_id": sequence_id, "status": "unknown"})
        if data.get("status") in {"queued", "processing", "completed", "completed_with_errors",
                                  "failed", "cancelled", "incomplete", "paused", "stopped",
                                  "running", "interrupted"}:
            receipt["status"] = data["status"]
        if publication and type(args.get("attempt_id")) is str:
            receipt["attempt_id"] = args["attempt_id"]
            receipt["attempt_revision"] = args["attempt_revision"]
        if action == "stop":
            receipt["run_id"] = args["run_id"]
        if action == "continue":
            run_id = data.get("run_id")
            if run_id is not None and (type(run_id) is not str or re.fullmatch(r"[0-9a-f]{32}", run_id) is None):
                raise HextileClientError("Fractal Continue acknowledgement unknown; GET the known sequence",
                                         kind="fractal_sequence_outcome_unknown", status_code=202,
                                         receipt={"sequence_id": sequence_id, "status": "unknown"})
            receipt["run_id"] = run_id
        return receipt

    # ── Shader output tools ─────────────────────────────────────────────

    def _shader_output_post(self, operation: str, args: Mapping[str, Any], path: str) -> dict:
        _shader_output_args(operation, args)
        if ((operation in {"preflight", "still"} and args.get("profile") == "shader-raster-still/1")
                or operation == "preflight" and (args.get("allow_unpreviewed_revision") is True
                    or args.get("profile") == "shader-linear-rgba-exr/1"
                    and args["output"].get("projection", "equirectangular") != "equirectangular")):
            self._require_native_render(still_profile=args["profile"])
        try:
            result = self.request_json("POST", path, dict(args), timeout=LONG_OPERATION_TIMEOUT_S)
        except HextileClientError as exc:
            if exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError(
                    "Shader output outcome unknown; inspect the original request_id without reposting.",
                    kind="shader_output_outcome_unknown", receipt={"request_id": args["request_id"]}) from exc
            raise
        return _shader_output_receipt(operation, args, result, mutation=True)

    def request_shader_preview(self, args: Mapping[str, Any]) -> dict:
        return self._shader_output_post("preview", args, "/api/shaders/agent-operations/output/preview")

    def preflight_shader_still(self, args: Mapping[str, Any]) -> dict:
        return self._shader_output_post("preflight", args, "/api/shaders/agent-operations/output/still/preflight")

    def export_shader_still(self, args: Mapping[str, Any]) -> dict:
        return self._shader_output_post("still", args, "/api/shaders/agent-operations/output/still")

    def get_shader_preview(self, args: Mapping[str, Any]) -> dict | bytes:
        _shader_output_args("get_preview", args)
        params = {"origin": args["shader"]["origin"], "shader_id": args["shader"]["shaderId"],
                  "project_context_witness": args["project_context_witness"]}
        if args.get("image") is True:
            return self.request_shader_preview_image(args["request_id"], params)
        return _shader_output_receipt("get_preview", args,
            self.request_json("GET", "/api/shaders/agent-operations/output/preview/" + args["request_id"],
                              params=params))

    def release_shader_preview(self, args: Mapping[str, Any]) -> dict:
        _shader_output_args("release_preview", args)
        return _shader_output_receipt("release_preview", args,
            self.request_json("DELETE", "/api/shaders/agent-operations/output/preview/" + args["request_id"],
                              {key: args[key] for key in ("shader", "project_context_witness")}), mutation=True)

    def get_shader_output_job(self, args: Mapping[str, Any]) -> dict:
        _shader_output_args("get_job", args)
        return _shader_output_receipt("get_job", args, self.request_json("GET", "/api/shaders/agent-operations/output/jobs/" + args["request_id"],
            params={"profile": args["profile"], "origin": args["shader"]["origin"],
                    "shader_id": args["shader"]["shaderId"],
                    "project_context_witness": args["project_context_witness"]}))

    def stop_shader_output_job(self, args: Mapping[str, Any]) -> dict:
        _shader_output_args("stop_job", args)
        try:
            return _shader_output_receipt("stop_job", args,
                self.request_json("POST", "/api/shaders/agent-operations/output/jobs/" + args["request_id"] + "/stop",
                    {key: args[key] for key in ("shader", "project_context_witness", "profile")}), mutation=True)
        except HextileClientError as exc:
            if exc.kind == "app_down" or exc.status_code is None or exc.status_code >= 500:
                raise HextileClientError("Shader output stop outcome unknown; read the original job status.",
                    kind="shader_output_outcome_unknown", receipt={"request_id": args["request_id"]}) from exc
            raise

    def export_shader_bundle(self, args: Mapping[str, Any]) -> dict:
        return self._shader_output_post("bundle", args, "/api/shaders/agent-operations/output/bundle")

    def export_shader_to_project(self, args: Mapping[str, Any]) -> dict:
        return self._shader_output_post("project", args, "/api/shaders/agent-operations/output/project")

    # ── internals ───────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path


def error_payload(exc: BaseException) -> dict[str, Any]:
    """Stable tool-result shaped error for MCP content."""
    if isinstance(exc, HextileClientError):
        payload: dict[str, Any] = {
            "ok": False,
            "error": str(exc),
            "kind": exc.kind,
            "status_code": exc.status_code,
        }
        if exc.kind == "capability":
            payload["code"] = "batch_unavailable"
        if exc.receipt is not None:
            payload["receipt"] = exc.receipt
        return payload
    return {"ok": False, "error": str(exc), "kind": "other"}
