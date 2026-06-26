package com.engonow.lms.service;

import com.engonow.lms.dto.SpeakingWebhookPayload;

public interface WebhookService {
    void handleAiSpeakingCallback(SpeakingWebhookPayload payload);
}
