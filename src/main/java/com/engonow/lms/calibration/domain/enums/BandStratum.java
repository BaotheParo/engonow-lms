package com.engonow.lms.calibration.domain.enums;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

import java.util.Arrays;

@Getter
@RequiredArgsConstructor
public enum BandStratum {
    STRATUM_4_0_4_5("4.0-4.5"),
    STRATUM_5_0_5_5("5.0-5.5"),
    STRATUM_6_0_6_5("6.0-6.5"),
    STRATUM_7_0_7_5("7.0-7.5"),
    STRATUM_8_0_8_5("8.0-8.5");

    private final String code;

    @JsonValue
    public String getCode() {
        return code;
    }

    @JsonCreator
    public static BandStratum fromCode(String code) {
        if (code == null) {
            return null;
        }
        return Arrays.stream(values())
                .filter(s -> s.code.equalsIgnoreCase(code.trim()))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Unknown BandStratum: " + code));
    }

    @Converter(autoApply = true)
    public static class BandStratumConverter implements AttributeConverter<BandStratum, String> {
        @Override
        public String convertToDatabaseColumn(BandStratum attribute) {
            return attribute != null ? attribute.getCode() : null;
        }

        @Override
        public BandStratum convertToEntityAttribute(String dbData) {
            return dbData != null ? BandStratum.fromCode(dbData) : null;
        }
    }
}
