package com.engonow.lms.mapper;

import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.entity.SpeakingSessionResult;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.Named;
import org.mapstruct.ReportingPolicy;

import java.math.BigDecimal;
import java.math.RoundingMode;

@Mapper(componentModel = "spring", unmappedTargetPolicy = ReportingPolicy.IGNORE)
public interface SpeakingMapper {

    @Mapping(source = "sessionId", target = "sessionId")
    @Mapping(source = "feedbackText", target = "aiFeedback")
    @Mapping(source = "payload", target = "aiScore", qualifiedByName = "calculateAiScore")
    SpeakingSessionResult toEntity(SpeakingWebhookPayload payload);

    @Named("calculateAiScore")
    default BigDecimal calculateAiScore(SpeakingWebhookPayload payload) {
        if (payload == null) return null;
        BigDecimal sum = payload.pronunciationScore()
            .add(payload.fluencyScore())
            .add(payload.lexicalScore())
            .add(payload.grammarScore());
        return sum.divide(BigDecimal.valueOf(4), 2, RoundingMode.HALF_UP);
    }
}
