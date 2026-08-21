package com.engonow.lms.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;

/**
 * Claim-Check remote audio pointer reference.
 * Strictly avoids transmitting binary audio on message brokers.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record AudioReferenceDTO(
    @NotBlank(message = "Storage provider must not be blank")
    String storageProvider,

    @NotBlank(message = "Storage bucket must not be blank")
    String bucket,

    @NotBlank(message = "Object key must not be blank")
    String objectKey,

    @NotBlank(message = "Checksum SHA-256 must not be blank")
    @Pattern(regexp = "^[a-fA-F0-9]{64}$", message = "Checksum must be a 64-character hexadecimal SHA-256 hash")
    String checksumSha256,

    @NotBlank(message = "Content type must not be blank")
    String contentType,

    @NotNull(message = "Duration in seconds must not be null")
    @Positive(message = "Duration in seconds must be positive")
    Double durationSeconds
) {}
