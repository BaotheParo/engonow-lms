package com.engonow.lms.publisher;

import com.engonow.lms.entity.OutboxEvent;

@FunctionalInterface
public interface MessagePublisher {

    void publish(OutboxEvent event);
}
