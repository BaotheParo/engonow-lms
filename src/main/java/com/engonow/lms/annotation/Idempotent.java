package com.engonow.lms.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.concurrent.TimeUnit;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Idempotent {
    /**
     * SpEL expression to extract the idempotency key dynamically.
     * E.g., "#payload.sessionId"
     */
    String key();

    /**
     * Prefix for the idempotency key to prevent namespace collisions.
     */
    String prefix() default "";

    /**
     * Lock expiration/holding duration.
     */
    long expireTime() default 5;

    /**
     * Time unit for lock expiration.
     */
    TimeUnit timeUnit() default TimeUnit.MINUTES;
}
