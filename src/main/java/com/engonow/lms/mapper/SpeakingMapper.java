package com.engonow.lms.mapper;

import com.engonow.lms.dto.SpeakingWebhookPayload;
import com.engonow.lms.entity.SpeakingSessionResult;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.ReportingPolicy;

@Mapper(componentModel = "spring", unmappedTargetPolicy = ReportingPolicy.IGNORE)
public interface SpeakingMapper {

    @Mapping(source = "sessionId", target = "sessionId")
    @Mapping(source = "feedbackText", target = "feedbackText")
    @Mapping(target = "selfCorrectionsText", ignore = true)
    @Mapping(target = "evidencesText", ignore = true)
    SpeakingSessionResult toEntity(SpeakingWebhookPayload payload);
}
