package com.engonow.lms.writing.controller;

import com.engonow.lms.service.RealtimeDeliveryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.UUID;

@RestController
@RequestMapping({"/api/v1/writing-submissions", "/api/v1/writing/submissions"})
@Tag(name = "Writing Real-Time Events", description = "Server-Sent Events (SSE) stream for live AI writing scoring updates")
@RequiredArgsConstructor
@Slf4j
public class WritingSubmissionEventsController {

    private final RealtimeDeliveryService realtimeDeliveryService;

    @GetMapping(value = "/{id}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @org.springframework.security.access.prepost.PreAuthorize("hasRole('ADMIN') or @submissionSecurityService.isWritingOwner(authentication, #id)")
    @Operation(
        summary = "Subscribe to live writing submission status events",
        description = "Establishes a Server-Sent Events (SSE) connection to receive real-time status transitions (PENDING -> PROCESSING -> SCORED/FAILED)."
    )
    public SseEmitter subscribeToWritingEvents(
            @PathVariable("id") UUID id,
            jakarta.servlet.http.HttpServletResponse response) {
        if (response != null) {
            response.setHeader("X-Accel-Buffering", "no");
            response.setHeader("Cache-Control", "no-cache, no-transform");
        }
        log.info("[SSE CONNECT] Client connected to live events for writing submission {}", id);
        return realtimeDeliveryService.subscribeToSubmissionEvents("WRITING", id);
    }
}
