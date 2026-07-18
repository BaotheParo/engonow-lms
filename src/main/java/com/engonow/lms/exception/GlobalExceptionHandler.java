package com.engonow.lms.exception;

import com.engonow.lms.dto.ErrorResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;

import java.time.LocalDateTime;

@RestControllerAdvice
@Slf4j
public class GlobalExceptionHandler {

    @ExceptionHandler(IdempotencyException.class)
    public ResponseEntity<ErrorResponse> handleIdempotencyException(IdempotencyException e, WebRequest request) {
        log.warn("IdempotencyException: {}", e.getMessage());
        ErrorResponse errorResponse = new ErrorResponse(
                LocalDateTime.now(),
                HttpStatus.CONFLICT.value(),
                HttpStatus.CONFLICT.getReasonPhrase(),
                e.getMessage(),
                request.getDescription(false).replace("uri=", "")
        );
        return ResponseEntity.status(HttpStatus.CONFLICT).body(errorResponse);
    }

    @ExceptionHandler(SlotNotAvailableException.class)
    public ResponseEntity<ErrorResponse> handleSlotNotAvailableException(SlotNotAvailableException e, WebRequest request) {
        log.warn("SlotNotAvailableException: {}", e.getMessage());
        ErrorResponse errorResponse = new ErrorResponse(
                LocalDateTime.now(),
                HttpStatus.BAD_REQUEST.value(),
                HttpStatus.BAD_REQUEST.getReasonPhrase(),
                e.getMessage(),
                request.getDescription(false).replace("uri=", "")
        );
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(errorResponse);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ErrorResponse> handleIllegalArgumentException(IllegalArgumentException e, WebRequest request) {
        log.warn("IllegalArgumentException: {}", e.getMessage());
        ErrorResponse errorResponse = new ErrorResponse(
                LocalDateTime.now(),
                HttpStatus.BAD_REQUEST.value(),
                HttpStatus.BAD_REQUEST.getReasonPhrase(),
                e.getMessage(),
                request.getDescription(false).replace("uri=", "")
        );
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(errorResponse);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleMethodArgumentNotValidException(MethodArgumentNotValidException e, WebRequest request) {
        String defaultMessage = "Validation failed";
        FieldError fieldError = e.getBindingResult().getFieldError();
        if (fieldError != null && fieldError.getDefaultMessage() != null) {
            defaultMessage = fieldError.getDefaultMessage();
        }
        log.warn("MethodArgumentNotValidException: {}", defaultMessage);

        ErrorResponse errorResponse = new ErrorResponse(
                LocalDateTime.now(),
                HttpStatus.BAD_REQUEST.value(),
                HttpStatus.BAD_REQUEST.getReasonPhrase(),
                defaultMessage,
                request.getDescription(false).replace("uri=", "")
        );
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(errorResponse);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleFallbackException(Exception e, WebRequest request) {
        org.springframework.web.bind.annotation.ResponseStatus responseStatus = 
                org.springframework.core.annotation.AnnotatedElementUtils.findMergedAnnotation(e.getClass(), org.springframework.web.bind.annotation.ResponseStatus.class);

        if (responseStatus != null) {
            HttpStatus status = responseStatus.value();
            log.warn("ResponseStatus exception encountered [{}]: {}", status, e.getMessage());
            ErrorResponse errorResponse = new ErrorResponse(
                    LocalDateTime.now(),
                    status.value(),
                    status.getReasonPhrase(),
                    e.getMessage(),
                    request.getDescription(false).replace("uri=", "")
            );
            return ResponseEntity.status(status).body(errorResponse);
        }

        log.error("Unhandled infrastructure exception occurred", e);
        ErrorResponse errorResponse = new ErrorResponse(
                LocalDateTime.now(),
                HttpStatus.INTERNAL_SERVER_ERROR.value(),
                HttpStatus.INTERNAL_SERVER_ERROR.getReasonPhrase(),
                "An unexpected error occurred on the server",
                request.getDescription(false).replace("uri=", "")
        );
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(errorResponse);
    }
}
