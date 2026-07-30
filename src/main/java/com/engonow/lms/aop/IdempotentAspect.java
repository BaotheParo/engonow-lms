package com.engonow.lms.aop;

import com.engonow.lms.annotation.Idempotent;
import com.engonow.lms.exception.IdempotencyException;
import com.engonow.lms.repository.IdempotencyRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.expression.EvaluationContext;
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.stereotype.Component;

import java.lang.reflect.Method;

@Aspect
@Component
@RequiredArgsConstructor
@Slf4j
public class IdempotentAspect {

    private final IdempotencyRepository idempotencyRepository;
    private final ExpressionParser expressionParser = new SpelExpressionParser();

    @Around("@annotation(idempotent)")
    public Object enforceIdempotency(ProceedingJoinPoint joinPoint, Idempotent idempotent) throws Throwable {
        MethodSignature signature = (MethodSignature) joinPoint.getSignature();
        Method method = signature.getMethod();
        String[] parameterNames = signature.getParameterNames();
        Object[] args = joinPoint.getArgs();

        // 1. Populate SpEL evaluation context with method arguments
        EvaluationContext context = new StandardEvaluationContext();
        if (parameterNames != null && args != null) {
            for (int i = 0; i < parameterNames.length; i++) {
                context.setVariable(parameterNames[i], args[i]);
            }
        }

        // 2. Parse key using SpEL
        String rawKey;
        try {
            Expression expression = expressionParser.parseExpression(idempotent.key());
            Object value = expression.getValue(context);
            rawKey = value != null ? value.toString() : "";
        } catch (Exception e) {
            log.error("Failed to parse SpEL expression for idempotency key on method {}: {}", method.getName(), e.getMessage());
            throw new IllegalArgumentException("Invalid idempotency key expression: " + idempotent.key(), e);
        }

        if (rawKey.isEmpty()) {
            log.warn("Resolved empty idempotency key for method {}. Skipping lock enforcement.", method.getName());
            return joinPoint.proceed();
        }

        // 3. Form final key
        String finalKey = idempotent.prefix().isEmpty() ? rawKey : idempotent.prefix() + ":" + rawKey;

        // 4. Convert expiration to milliseconds
        long ttlMillis = idempotent.timeUnit().toMillis(idempotent.expireTime());

        log.debug("Checking idempotency for key: {} (TTL: {}ms) on method: {}", finalKey, ttlMillis, method.getName());

        // 5. Try lock
        boolean locked = idempotencyRepository.tryLock(finalKey, ttlMillis);
        if (!locked) {
            log.warn("Duplicate request detected for key: {} on method: {}", finalKey, method.getName());
            throw new IdempotencyException(
                    "Request is already completed or currently processing.");
        }

        // 6. Execute the method and release the lock only when business processing fails
        Object result;
        try {
            result = joinPoint.proceed();
        } catch (Throwable throwable) {
            idempotencyRepository.releaseLock(finalKey);
            throw throwable;
        }

        // 7. Preserve the lock as COMPLETED for the remainder of its TTL
        idempotencyRepository.completeLock(finalKey, ttlMillis);
        return result;
    }
}
