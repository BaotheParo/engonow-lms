package com.engonow.lms.exception;

public class IdempotencyException extends RuntimeException {
    
    public IdempotencyException(String message) {
        super(message);
    }
}
