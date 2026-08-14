package com.engonow.lms.writing.exception;

import com.engonow.lms.writing.domain.enums.SubmissionStatus;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

import java.util.UUID;

@ResponseStatus(HttpStatus.UNPROCESSABLE_ENTITY)
public class WritingSubmissionProcessingException extends RuntimeException {

    public WritingSubmissionProcessingException(UUID submissionId, SubmissionStatus status) {
        super("Writing submission " + submissionId + " is currently in " + status + " status. Results are not ready.");
    }

    public WritingSubmissionProcessingException(String message) {
        super(message);
    }
}
