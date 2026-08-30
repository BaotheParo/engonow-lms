package com.engonow.lms.security;

import com.engonow.lms.config.SecurityConfig;
import com.engonow.lms.logging.PiiSanitizingLogbackFilter;
import com.engonow.lms.service.RealtimeDeliveryService;
import com.engonow.lms.service.SubmissionSecurityService;
import com.engonow.lms.service.impl.SubmissionSecurityServiceImpl;
import com.engonow.lms.writing.controller.WritingSubmissionEventsController;
import com.engonow.lms.writing.domain.entity.WritingSubmission;
import com.engonow.lms.writing.repository.WritingSubmissionRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = {WritingSubmissionEventsController.class})
@Import({SecurityConfig.class, SubmissionSecurityServiceImpl.class})
public class SecurityAndSanitizationIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private RealtimeDeliveryService realtimeDeliveryService;

    @MockBean
    private WritingSubmissionRepository writingSubmissionRepository;

    private UUID targetSubmissionId;
    private UUID ownerStudentId;
    private UUID foreignStudentId;

    @BeforeEach
    void setUp() {
        targetSubmissionId = UUID.randomUUID();
        ownerStudentId = UUID.randomUUID();
        foreignStudentId = UUID.randomUUID();

        WritingSubmission submission = new WritingSubmission();
        submission.setId(targetSubmissionId);
        submission.setStudentId(ownerStudentId);

        when(writingSubmissionRepository.findById(targetSubmissionId)).thenReturn(Optional.of(submission));
        when(realtimeDeliveryService.subscribeToSubmissionEvents(any(), any())).thenReturn(new SseEmitter());
    }

    @Test
    @DisplayName("Test 1: Anonymous Access to Protected Endpoints Returns 401 Unauthorized")
    void testAnonymousAccessReturns401() throws Exception {
        mockMvc.perform(get("/api/v1/writing-submissions/{id}/events", targetSubmissionId))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.status").value(401))
            .andExpect(jsonPath("$.error").value("Unauthorized"));
    }

    @Test
    @DisplayName("Test 2: Student Access to Admin Calibration Endpoints Returns 403 Forbidden")
    @WithMockUser(username = "student_user", roles = {"STUDENT"})
    void testStudentAccessToAdminReturns403() throws Exception {
        mockMvc.perform(get("/api/v1/admin/calibration/corpus-items"))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.status").value(403))
            .andExpect(jsonPath("$.error").value("Forbidden"));
    }

    @Test
    @DisplayName("Test 3: Unauthorized Student Connecting to Foreign Submission SSE Returns 403 Forbidden")
    @WithMockUser(username = "00000000-0000-0000-0000-000000000999", roles = {"STUDENT"})
    void testUnauthorizedStudentAccessToForeignSubmissionSseReturns403() throws Exception {
        mockMvc.perform(get("/api/v1/writing-submissions/{id}/events", targetSubmissionId)
                .accept(MediaType.TEXT_EVENT_STREAM))
            .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("Test 4: Submission Owner Successfully Establishes SSE Stream")
    void testAuthorizedOwnerAccessToSseStreamSucceeds() throws Exception {
        mockMvc.perform(get("/api/v1/writing-submissions/{id}/events", targetSubmissionId)
                .header("X-User-Id", ownerStudentId.toString())
                .header("X-User-Role", "ROLE_STUDENT")
                .accept(MediaType.TEXT_EVENT_STREAM))
            .andExpect(status().isOk());
    }

    @Test
    @DisplayName("Test 5: PII Logback Filter Redacts AWS/GCP Presigned Signatures and Bearer Tokens")
    void testPiiSanitizingLogbackFilter() {
        String rawLog = "Audio upload successful: https://s3.amazonaws.com/bucket/audio.wav?X-Amz-Signature=abcd1234efgh&expires=3600 with header Authorization: Bearer secret_jwt_token_999";
        String sanitized = PiiSanitizingLogbackFilter.sanitize(rawLog);

        assertThat(sanitized).doesNotContain("abcd1234efgh");
        assertThat(sanitized).doesNotContain("secret_jwt_token_999");
        assertThat(sanitized).contains("X-Amz-Signature=[REDACTED]");
        assertThat(sanitized).contains("Bearer [REDACTED]");
    }
}
