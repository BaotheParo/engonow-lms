package com.engonow.lms.service;

import org.springframework.security.core.Authentication;

import java.util.UUID;

public interface SubmissionSecurityService {

    /**
     * Verifies if the authenticated principal is the owner of the target writing submission
     * or possesses administrator privileges (ROLE_ADMIN).
     *
     * @param authentication current security context authentication
     * @param submissionId target writing submission UUID
     * @return true if owner or admin, false otherwise
     */
    boolean isWritingOwner(Authentication authentication, UUID submissionId);

    /**
     * Direct UUID comparison helper for writing submission ownership.
     */
    boolean isWritingOwner(UUID submissionId, UUID studentId);

    /**
     * Verifies if the authenticated principal is the owner of the target speaking attempt
     * or possesses administrator privileges (ROLE_ADMIN).
     *
     * @param authentication current security context authentication
     * @param submissionId target speaking attempt UUID
     * @return true if owner or admin, false otherwise
     */
    boolean isSpeakingOwner(Authentication authentication, UUID submissionId);

    /**
     * Direct UUID comparison helper for speaking attempt ownership.
     */
    boolean isSpeakingOwner(UUID submissionId, UUID studentId);
}
