"""Stable public errors; never return raw exception details or input values."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from sales_manager_api.repository import StorageError
from sales_manager_api.schemas import ErrorBody, ErrorDetail, ErrorResponse

HTTP_ERRORS = {
    400: ("INVALID_REQUEST", "リクエストを確認してください。"),
    401: ("UNAUTHENTICATED", "認証が必要です。"),
    403: ("FORBIDDEN", "この操作は許可されていません。"),
    404: ("NOT_FOUND", "対象が見つかりません。"),
    405: ("METHOD_NOT_ALLOWED", "このHTTPメソッドは利用できません。"),
    500: ("INTERNAL_ERROR", "処理に失敗しました。"),
}


class ApplicationError(Exception):
    """Only explicitly public messages belong in this exception."""

    def __init__(self, status_code: int, code: str, public_message: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.public_message = public_message


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            request_id=request.state.request_id,
            details=details or [],
        )
    )
    return JSONResponse(
        body.model_dump(mode="json"), status_code=status, headers=headers
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code, message = HTTP_ERRORS.get(
            exc.status_code, ("HTTP_ERROR", "リクエストを処理できませんでした。")
        )
        return error_response(
            request, exc.status_code, code, message, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        if any(error["type"] == "json_invalid" for error in exc.errors()):
            return error_response(
                request, 400, "INVALID_JSON", "JSONの形式を確認してください。"
            )
        details = [
            ErrorDetail(
                path=".".join(str(part) for part in error["loc"]),
                code=error["type"],
                message="入力内容を確認してください。",
            )
            for error in exc.errors()
        ]
        return error_response(
            request, 422, "VALIDATION_ERROR", "入力内容を確認してください。", details
        )

    @app.exception_handler(ApplicationError)
    async def application_error(
        request: Request, exc: ApplicationError
    ) -> JSONResponse:
        return error_response(
            request,
            exc.status_code,
            exc.code,
            exc.public_message,
            headers={"Retry-After": "1"} if exc.status_code == 503 else None,
        )

    @app.exception_handler(StorageError)
    async def storage_error(request: Request, exc: StorageError) -> JSONResponse:
        return error_response(
            request,
            503,
            "TEMPORARILY_UNAVAILABLE",
            "保存先を利用できません。",
            headers={"Retry-After": "1"},
        )
