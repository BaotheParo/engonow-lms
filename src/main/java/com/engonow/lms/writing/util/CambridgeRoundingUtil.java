package com.engonow.lms.writing.util;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Deterministic IELTS writing band calculations using decimal arithmetic only.
 */
public final class CambridgeRoundingUtil {

    private static final BigDecimal MINIMUM_BAND = new BigDecimal("0.0");
    private static final BigDecimal MAXIMUM_BAND = new BigDecimal("9.0");
    private static final BigDecimal HALF_BAND = new BigDecimal("0.5");
    private static final BigDecimal QUARTER_BAND = new BigDecimal("0.25");
    private static final BigDecimal THREE_QUARTER_BAND = new BigDecimal("0.75");
    private static final BigDecimal ONE = BigDecimal.ONE;
    private static final BigDecimal CRITERION_COUNT = BigDecimal.valueOf(4L);

    private CambridgeRoundingUtil() {
    }

    /**
     * Calculates the overall writing band from the four equally weighted
     * criterion bands.
     *
     * @param ta  task achievement/task response band
     * @param cc  coherence and cohesion band
     * @param lr  lexical resource band
     * @param gra grammatical range and accuracy band
     * @return the Cambridge-rounded overall band, with a scale of one
     * @throws IllegalArgumentException if a criterion is null, outside the
     *                                  inclusive range 0.0 to 9.0, or is not
     *                                  a multiple of 0.5
     */
    public static BigDecimal calculateOverallBand(
        BigDecimal ta,
        BigDecimal cc,
        BigDecimal lr,
        BigDecimal gra
    ) {
        requireLegalCriterion("ta", ta);
        requireLegalCriterion("cc", cc);
        requireLegalCriterion("lr", lr);
        requireLegalCriterion("gra", gra);

        BigDecimal mean = ta.add(cc)
            .add(lr)
            .add(gra)
            .divide(CRITERION_COUNT, 3, RoundingMode.HALF_UP);

        return applyCambridgeRounding(mean);
    }

    /**
     * Applies Cambridge rounding to a four-criterion mean. The mean is first
     * rounded to the nearest quarter band; quarter and three-quarter values
     * are then promoted to the next half or whole band respectively.
     *
     * @param mean arithmetic mean to round
     * @return a value in the inclusive range 0.0 to 9.0, with a scale of one
     * @throws IllegalArgumentException if {@code mean} is null
     */
    public static BigDecimal applyCambridgeRounding(BigDecimal mean) {
        if (mean == null) {
            throw new IllegalArgumentException("mean must not be null");
        }

        BigDecimal roundedToQuarter = mean
            .divide(QUARTER_BAND, 0, RoundingMode.HALF_UP)
            .multiply(QUARTER_BAND);

        if (roundedToQuarter.compareTo(MINIMUM_BAND) < 0) {
            return MINIMUM_BAND;
        }
        if (roundedToQuarter.compareTo(MAXIMUM_BAND) > 0) {
            return MAXIMUM_BAND;
        }

        BigDecimal decimalPart = roundedToQuarter.remainder(ONE);
        BigDecimal roundedBand = decimalPart.compareTo(QUARTER_BAND) == 0
            || decimalPart.compareTo(THREE_QUARTER_BAND) == 0
            ? roundedToQuarter.add(QUARTER_BAND)
            : roundedToQuarter;

        return roundedBand
            .max(MINIMUM_BAND)
            .min(MAXIMUM_BAND)
            .setScale(1, RoundingMode.HALF_UP);
    }

    /**
     * Determines whether a value is a legal criterion band.
     *
     * @param value candidate criterion score
     * @return {@code true} only for non-null half-band values from 0.0 to 9.0
     */
    public static boolean isLegalBandValue(BigDecimal value) {
        return value != null
            && value.compareTo(MINIMUM_BAND) >= 0
            && value.compareTo(MAXIMUM_BAND) <= 0
            && value.remainder(HALF_BAND).compareTo(BigDecimal.ZERO) == 0;
    }

    private static void requireLegalCriterion(String criterion, BigDecimal value) {
        if (!isLegalBandValue(value)) {
            throw new IllegalArgumentException(
                criterion + " must be a multiple of 0.5 within the range [0.0, 9.0]"
            );
        }
    }
}
