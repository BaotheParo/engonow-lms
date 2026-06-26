package com.engonow.lms.service.impl;

import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.entity.MockTestBooking;
import com.engonow.lms.entity.SpeakingSessionResult;
import com.engonow.lms.exception.DuplicateWebhookException;
import com.engonow.lms.mapper.SpeakingMapper;
import com.engonow.lms.repository.MockTestBookingRepository;
import com.engonow.lms.repository.SpeakingSessionResultRepository;
import com.engonow.lms.service.WebhookService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;

@Service
public class WebhookServiceImpl implements WebhookService {

    private final SpeakingSessionResultRepository speakingSessionResultRepository;
    private final MockTestBookingRepository mockTestBookingRepository;
    private final SpeakingMapper speakingMapper;

    public WebhookServiceImpl(
            SpeakingSessionResultRepository speakingSessionResultRepository,
            MockTestBookingRepository mockTestBookingRepository,
            SpeakingMapper speakingMapper) {
        this.speakingSessionResultRepository = speakingSessionResultRepository;
        this.mockTestBookingRepository = mockTestBookingRepository;
        this.speakingMapper = speakingMapper;
    }

    @Override
    @Transactional
    public void handleAiSpeakingCallback(SpeakingWebhookPayload payload) {
        // Idempotency protection
        if (speakingSessionResultRepository.findBySessionId(payload.sessionId()).isPresent()) {
            throw new DuplicateWebhookException("Speaking session result with sessionId " + payload.sessionId() + " already exists.");
        }

        // Fetch MockTestBooking (sessionId represents bookingId)
        Long bookingId;
        try {
            bookingId = Long.parseLong(payload.sessionId());
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Session ID must be a valid numeric booking ID: " + payload.sessionId());
        }

        MockTestBooking booking = mockTestBookingRepository.findById(bookingId)
                .orElseThrow(() -> new IllegalArgumentException("MockTestBooking not found for ID: " + bookingId));

        // Use SpeakingMapper to populate entity fields from payload
        SpeakingSessionResult result = speakingMapper.toEntity(payload);
        result.setBooking(booking);

        // Fallback tutor scores: 6.0 representing 20% weight
        BigDecimal fallbackTutorScore = BigDecimal.valueOf(6.0);
        result.setTutorFluencyScore(fallbackTutorScore);
        result.setTutorLexicalScore(fallbackTutorScore);
        result.setTutorGrammarScore(fallbackTutorScore);
        result.setTutorPronunciationScore(fallbackTutorScore);
        result.setTutorComments("Fallback automatic base evaluation");

        // Weighted average & IELTS rounding (nearest 0.5 or 0.0) is handled internally in computeFinalBand()
        result.computeFinalBand();

        // Save Entity
        speakingSessionResultRepository.save(result);
    }
}
