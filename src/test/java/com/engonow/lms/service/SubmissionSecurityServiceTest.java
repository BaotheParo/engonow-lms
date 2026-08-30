package com.engonow.lms.service;

import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
public class SubmissionSecurityServiceTest {

    @Mock
    private WritingSubmissionRepository writingSubmissionRepository;

    @Mock
    private SpeakingSessionResultRepository speakingSessionResultRepository;

    private SubmissionSecurityService submissionSecurityService;

    @BeforeEach
    void setUp() {
        submissionSecurityService = new com.engonow.lms.service.impl.SubmissionSecurityServiceImpl(
            writingSubmissionRepository,
            speakingSessionResultRepository
        );
    }

    @Test
    @DisplayName("Ownership check returns true when studentId matches submission owner")
    void testWritingOwnerMatch() {
        UUID submissionId = UUID.randomUUID();
        UUID studentId = UUID.randomUUID();

        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStudentId(studentId);

        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.of(submission));

        boolean isOwner = submissionSecurityService.isWritingOwner(submissionId, studentId);
        assertThat(isOwner).isTrue();
    }

    @Test
    @DisplayName("Ownership check returns false when studentId does not match submission owner")
    void testWritingOwnerMismatch() {
        UUID submissionId = UUID.randomUUID();
        UUID ownerId = UUID.randomUUID();
        UUID imposterId = UUID.randomUUID();

        WritingSubmission submission = new WritingSubmission();
        submission.setId(submissionId);
        submission.setStudentId(ownerId);

        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.of(submission));

        boolean isOwner = submissionSecurityService.isWritingOwner(submissionId, imposterId);
        assertThat(isOwner).isFalse();
    }

    @Test
    @DisplayName("Ownership check returns false when submission does not exist")
    void testWritingOwnerNotFound() {
        UUID submissionId = UUID.randomUUID();
        UUID studentId = UUID.randomUUID();

        when(writingSubmissionRepository.findById(submissionId)).thenReturn(Optional.empty());

        boolean isOwner = submissionSecurityService.isWritingOwner(submissionId, studentId);
        assertThat(isOwner).isFalse();
    }
}
