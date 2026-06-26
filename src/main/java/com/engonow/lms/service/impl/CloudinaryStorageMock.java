package com.engonow.lms.service.impl;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class CloudinaryStorageMock {
    private static final Logger log = LoggerFactory.getLogger(CloudinaryStorageMock.class);

    @Async("taskExecutor")
    public void uploadFileAsync(String filename, byte[] content) {
        log.info("[CLOUDINARY MOCK] Starting asynchronous upload for file: {} ({} bytes)", filename, content.length);
        try {
            // Simulate upload latency
            Thread.sleep(2000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        log.info("[CLOUDINARY MOCK] Asynchronous upload completed for file: {}", filename);
    }
}
