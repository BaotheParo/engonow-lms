package com.engonow.lms.writing.util;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;

import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
import java.math.BigDecimal;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CambridgeRoundingUtilTest {

    @ParameterizedTest
    @MethodSource("exactBandCases")
    void preservesExactWholeAndHalfBandBoundaries(
        String ta,
        String cc,
        String lr,
        String gra,
        String expected
    ) {
        BigDecimal result = CambridgeRoundingUtil.calculateOverallBand(
            band(ta), band(cc), band(lr), band(gra)
        );

        assertEquals(band(expected), result);
        assertEquals(1, result.scale());
    }

    @Test
    void roundsQuarterBandUpToNextHalfBand() {
        BigDecimal result = CambridgeRoundingUtil.calculateOverallBand(
            band("6.0"), band("6.0"), band("6.0"), band("6.5")
        );

        assertEquals(band("6.5"), result);
    }

    @Test
    void roundsThreeQuarterBandUpToNextWholeBand() {
        BigDecimal result = CambridgeRoundingUtil.calculateOverallBand(
            band("6.0"), band("6.5"), band("7.0"), band("7.0")
        );

        assertEquals(band("7.0"), result);
    }

    @ParameterizedTest
    @MethodSource("directRoundingCases")
    void appliesCambridgeRoundingAndClampsToLegalRange(String mean, String expected) {
        BigDecimal result = CambridgeRoundingUtil.applyCambridgeRounding(band(mean));

        assertEquals(band(expected), result);
        assertEquals(1, result.scale());
    }

    @Test
    void rejectsNullMean() {
        IllegalArgumentException exception = assertThrows(
            IllegalArgumentException.class,
            () -> CambridgeRoundingUtil.applyCambridgeRounding(null)
        );

        assertEquals("mean must not be null", exception.getMessage());
    }

    @ParameterizedTest
    @MethodSource("invalidCriterionPositions")
    void rejectsNullCriterionAtEveryPosition(
        BigDecimal ta,
        BigDecimal cc,
        BigDecimal lr,
        BigDecimal gra
    ) {
        assertThrows(
            IllegalArgumentException.class,
            () -> CambridgeRoundingUtil.calculateOverallBand(ta, cc, lr, gra)
        );
    }

    @ParameterizedTest
    @ValueSource(strings = {"-0.5", "9.5", "6.3"})
    void rejectsOutOfRangeOrNonHalfBandCriterion(String invalidScore) {
        assertThrows(
            IllegalArgumentException.class,
            () -> CambridgeRoundingUtil.calculateOverallBand(
                band(invalidScore), band("6.0"), band("6.0"), band("6.0")
            )
        );
    }

    @ParameterizedTest
    @NullSource
    @ValueSource(strings = {"-0.5", "9.5", "6.3"})
    void identifiesIllegalBandValues(String candidate) {
        BigDecimal value = candidate == null ? null : band(candidate);

        assertFalse(CambridgeRoundingUtil.isLegalBandValue(value));
    }

    @ParameterizedTest
    @ValueSource(strings = {"0.0", "0.5", "6.0", "6.5", "9.0", "9.00"})
    void identifiesLegalBandValues(String candidate) {
        assertTrue(CambridgeRoundingUtil.isLegalBandValue(band(candidate)));
    }

    @Test
    void isFinalAndCannotBePubliclyInstantiated() throws ReflectiveOperationException {
        Constructor<CambridgeRoundingUtil> constructor =
            CambridgeRoundingUtil.class.getDeclaredConstructor();

        assertTrue(Modifier.isFinal(CambridgeRoundingUtil.class.getModifiers()));
        assertTrue(Modifier.isPrivate(constructor.getModifiers()));

        constructor.setAccessible(true);
        assertNotNull(constructor.newInstance());
    }

    private static Stream<Arguments> exactBandCases() {
        return Stream.of(
            Arguments.of("6.0", "6.0", "6.0", "6.0", "6.0"),
            Arguments.of("6.5", "6.5", "6.5", "6.5", "6.5"),
            Arguments.of("0.0", "0.0", "0.0", "0.0", "0.0"),
            Arguments.of("9.0", "9.0", "9.0", "9.0", "9.0")
        );
    }

    private static Stream<Arguments> directRoundingCases() {
        return Stream.of(
            Arguments.of("6.00", "6.0"),
            Arguments.of("6.25", "6.5"),
            Arguments.of("6.50", "6.5"),
            Arguments.of("6.75", "7.0"),
            Arguments.of("7.125", "7.5"),
            Arguments.of("5.875", "6.0"),
            Arguments.of("-0.20", "0.0"),
            Arguments.of("9.30", "9.0")
        );
    }

    private static Stream<Arguments> invalidCriterionPositions() {
        BigDecimal valid = band("6.0");
        return Stream.of(
            Arguments.of(null, valid, valid, valid),
            Arguments.of(valid, null, valid, valid),
            Arguments.of(valid, valid, null, valid),
            Arguments.of(valid, valid, valid, null)
        );
    }

    private static BigDecimal band(String value) {
        return new BigDecimal(value);
    }
}
