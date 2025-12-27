"""Tool decorators for error handling."""

import functools
from collections.abc import Callable
from typing import Any

from ctm_mcp_server.data.git_repo import GitRepoError
from ctm_mcp_server.data.github_client import GitHubClientError


def ctm_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Standardize error handling and response format."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = await func(*args, **kwargs)
            if isinstance(result, dict) and "success" not in result:
                result["success"] = True
            return result  # type: ignore[no-any-return]

        except GitHubClientError as e:
            return {
                "success": False,
                "error": f"GitHub API error: {str(e)}",
                "error_type": "github_api",
            }
        except GitRepoError as e:
            return {
                "success": False,
                "error": f"Git repository error: {str(e)}",
                "error_type": "git_repo",
            }
        except ValueError as e:
            return {
                "success": False,
                "error": f"Invalid parameter: {str(e)}",
                "error_type": "validation",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "error_type": "unexpected",
            }

    return wrapper


def require_params(*param_names: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Validate required parameters are present and non-empty."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            import inspect

            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            missing = []
            for param in param_names:
                value = bound_args.arguments.get(param)
                if value is None or (isinstance(value, str) and not value.strip()):
                    missing.append(param)

            if missing:
                return {
                    "success": False,
                    "error": f"Missing required parameters: {', '.join(missing)}",
                    "error_type": "validation",
                }

            return await func(*args, **kwargs)  # type: ignore[no-any-return]

        return wrapper

    return decorator
