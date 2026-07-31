package com.engonow.lms.event;

import java.util.Objects;

/**
 * In-process result event used by LOCAL broker mode and tests.
 */
public record SpeakingResultLocalEvent(String payload) {

    public SpeakingResultLocalEvent {
        Objects.requireNonNull(payload, "payload must not be null");
    }
}
