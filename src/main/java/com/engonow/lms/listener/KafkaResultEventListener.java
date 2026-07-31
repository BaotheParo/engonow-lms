package com.engonow.lms.listener;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
@Slf4j
@RequiredArgsConstructor
@ConditionalOnProperty(name = "engonow.broker.type", havingValue = "KAFKA")
public class KafkaResultEventListener {

    private final SpeakingResultListener speakingResultListener;

    @KafkaListener(
            topics = "${engonow.broker.topics.speaking-results:ielts-speaking-results}",
            groupId = "${spring.kafka.consumer.group-id:engonow-lms-group}")
    public void onKafkaResultReceived(
            ConsumerRecord<String, String> record,
            Acknowledgment acknowledgment) {
        log.debug(
                "[KAFKA RESULT LISTENER] Received speaking result topic={} partition={} offset={}",
                record.topic(),
                record.partition(),
                record.offset());

        speakingResultListener.handleResultPayload(record.value());

        if (acknowledgment != null) {
            acknowledgment.acknowledge();
        }
    }
}
