package com.engonow.lms.admin.controller;

import com.engonow.lms.admin.dto.DlqReplayRequestDTO;
import com.engonow.lms.admin.dto.DlqReplayResponseDTO;
import com.engonow.lms.admin.service.KafkaDlqAdminService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/admin/kafka/dlq")
@RequiredArgsConstructor
@Slf4j
@Tag(name = "Kafka DLQ Admin", description = "Endpoints for Dead Letter Queue inspection and safe event replay")
public class KafkaDlqAdminController {

    private final KafkaDlqAdminService dlqAdminService;

    @PostMapping("/replay")
    @Operation(summary = "Replay messages from a DLQ topic back to its target topic")
    public ResponseEntity<DlqReplayResponseDTO> replayDlq(@Valid @RequestBody DlqReplayRequestDTO request) {
        log.info("[ADMIN REST API] Received DLQ replay request for topic {}", request.dlqTopic());
        DlqReplayResponseDTO response = dlqAdminService.replayDlqMessages(request);
        return ResponseEntity.ok(response);
    }
}
