package com.engonow.lms.logging;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.turbo.TurboFilter;
import ch.qos.logback.core.spi.FilterReply;
import org.slf4j.Marker;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * TurboFilter that sanitizes presigned object storage credentials, tokens,
 * and PII signatures from application logs in real-time.
 */
public class PiiSanitizingLogbackFilter extends TurboFilter {

    private static final Pattern SIGNATURE_PATTERN = Pattern.compile(
        "(?i)(X-Amz-Signature=|X-Goog-Signature=|signature=|sig=)[^&\\s\"]+"
    );

    private static final Pattern BEARER_TOKEN_PATTERN = Pattern.compile(
        "(?i)(Bearer\\s+)[a-zA-Z0-9_\\-\\.]+"
    );

    @Override
    public FilterReply decide(
        Marker marker,
        Logger logger,
        Level level,
        String format,
        Object[] params,
        Throwable t
    ) {
        if (params != null) {
            for (int i = 0; i < params.length; i++) {
                if (params[i] instanceof CharSequence) {
                    params[i] = sanitize(params[i].toString());
                }
            }
        }
        return FilterReply.NEUTRAL;
    }

    /**
     * Sanitizes sensitive credentials, presigned signatures, and tokens in a string.
     *
     * @param message raw log message or parameter
     * @return sanitized string with credentials redacted
     */
    public static String sanitize(String message) {
        if (message == null || message.isEmpty()) {
            return message;
        }

        Matcher sigMatcher = SIGNATURE_PATTERN.matcher(message);
        String cleaned = sigMatcher.replaceAll("$1[REDACTED]");

        Matcher bearerMatcher = BEARER_TOKEN_PATTERN.matcher(cleaned);
        return bearerMatcher.replaceAll("$1[REDACTED]");
    }
}
