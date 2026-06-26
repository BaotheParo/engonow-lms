package com.engonow.lms.controller;

import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.service.WebhookService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/callback")
public class WebhookCallbackController {

    private final WebhookService webhookService;

    public WebhookCallbackController(WebhookService webhookService) {
        this.webhookService = webhookService;
    }

    @PostMapping("/ai-grading")
    public ResponseEntity<Void> handleSpeakingWebhookCallback(
            @RequestBody @Valid SpeakingWebhookPayload payload) {
        webhookService.handleAiSpeakingCallback(payload);
        return ResponseEntity.ok().build();
    }
}
