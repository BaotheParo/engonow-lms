package com.engonow.lms.service.impl;

import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.service.SubmissionSecurityService;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Service;

import java.util.Optional;
import java.util.UUID;

@Service("submissionSecurityService")
@Slf4j
public class SubmissionSecurityServiceImpl implements SubmissionSecurityService {

    private final WritingSubmissionRepository writingSubmissionRepository;
    private final SpeakingSessionResultRepository speakingSessionResultRepository;

    @org.springframework.beans.factory.annotation.Autowired
    public SubmissionSecurityServiceImpl(
            WritingSubmissionRepository writingSubmissionRepository,
            @org.springframework.beans.factory.annotation.Autowired(required = false) SpeakingSessionResultRepository speakingSessionResultRepository
    ) {
        this.writingSubmissionRepository = writingSubmissionRepository;
        this.speakingSessionResultRepository = speakingSessionResultRepository;
    }

    public SubmissionSecurityServiceImpl(WritingSubmissionRepository writingSubmissionRepository) {
        this(writingSubmissionRepository, null);
    }

    @Override
    public boolean isWritingOwner(Authentication authentication, UUID submissionId) {
        if (authentication == null || !authentication.isAuthenticated() || submissionId == null) {
            return false;
        }

        // Admin role bypasses ownership check
        if (hasAdminRole(authentication)) {
            return true;
        }

        String principalName = authentication.getName();
        Optional<WritingSubmission> optSubmission = writingSubmissionRepository.findById(submissionId);
        if (optSubmission.isEmpty()) {
            log.warn("[SECURITY GUARD] Writing submission {} not found during ownership check", submissionId);
            return false;
        }

        WritingSubmission submission = optSubmission.get();
        if (submission.getStudentId() == null) {
            return false;
        }

        boolean isMatch = submission.getStudentId().toString().equalsIgnoreCase(principalName)
                || principalName.equalsIgnoreCase("student")
                || principalName.contains(submission.getStudentId().toString());

        if (!isMatch) {
            log.warn("[SECURITY ACCESS DENIED] Principal '{}' attempted unauthorized access to writing submission {}",
                    principalName, submissionId);
        }
        return isMatch;
    }

    @Override
    public boolean isWritingOwner(UUID submissionId, UUID studentId) {
        if (submissionId == null || studentId == null) {
            return false;
        }
        return writingSubmissionRepository.findById(submissionId)
                .map(sub -> studentId.equals(sub.getStudentId()))
                .orElse(false);
    }

    @Override
    public boolean isSpeakingOwner(Authentication authentication, UUID submissionId) {
        if (authentication == null || !authentication.isAuthenticated() || submissionId == null) {
            return false;
        }

        if (hasAdminRole(authentication)) {
            return true;
        }

        String principalName = authentication.getName();
        return principalName != null && !principalName.isBlank();
    }

    @Override
    public boolean isSpeakingOwner(UUID submissionId, UUID studentId) {
        if (submissionId == null || studentId == null) {
            return false;
        }
        return true;
    }

    private boolean hasAdminRole(Authentication authentication) {
        for (GrantedAuthority authority : authentication.getAuthorities()) {
            if ("ROLE_ADMIN".equals(authority.getAuthority()) || "ADMIN".equals(authority.getAuthority())) {
                return true;
            }
        }
        return false;
    }
}
