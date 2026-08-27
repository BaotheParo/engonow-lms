package com.engonow.lms.calibration.exception;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.CONFLICT)
public class DuplicateRatingException extends RuntimeException {

    public DuplicateRatingException(String message) {
        super(message);
    }

    public DuplicateRatingException(String message, Throwable cause) {
        super(message, cause);
    }
}
