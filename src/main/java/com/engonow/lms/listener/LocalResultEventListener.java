package com.engonow.lms.listener;

import com.engonow.lms.event.SpeakingResultLocalEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
@Slf4j
@RequiredArgsConstructor
@ConditionalOnProperty(
        name = "engonow.broker.type",
        havingValue = "LOCAL",
        matchIfMissing = true)
public class LocalResultEventListener {

    private final SpeakingResultListener speakingResultListener;

    @EventListener
    public void onLocalResultReceived(SpeakingResultLocalEvent event) {
        log.debug("[LOCAL RESULT LISTENER] Received speaking result event");
        speakingResultListener.handleResultPayload(event.payload());
    }
}
