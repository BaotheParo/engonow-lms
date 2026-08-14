package com.engonow.lms.writing.exception;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

import java.util.UUID;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class WritingSubmissionNotFoundException extends RuntimeException {

    public WritingSubmissionNotFoundException(UUID submissionId) {
        super("Writing submission not found for ID: " + submissionId);
    }

    public WritingSubmissionNotFoundException(UUID submissionId, UUID studentId) {
        super("Writing submission not found for ID: " + submissionId + " and student: " + studentId);
    }

    public WritingSubmissionNotFoundException(String message) {
        super(message);
    }
}
