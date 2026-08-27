package com.engonow.lms.calibration.util;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * Two-Way Mixed Single-Score Consistency Intraclass Correlation Coefficient ICC(3,1) Calculator.
 * <p>
 * Evaluates inter-rater reliability across a pool of human examiners using Two-Way ANOVA without replication:
 * <pre>
 * ICC(3,1) = (MS_Rows - MS_Error) / (MS_Rows + (k - 1) * MS_Error)
 * </pre>
 * where:
 * <ul>
 *   <li>MS_Rows = Mean Square between items/rows (variance between test items)</li>
 *   <li>MS_Columns = Mean Square between raters/columns (systematic rater bias)</li>
 *   <li>MS_Error = Mean Square error / residual (random measurement noise)</li>
 *   <li>k = number of raters per item</li>
 *   <li>n = number of items</li>
 * </ul>
 */
public final class IccCalculator {

    private IccCalculator() {}

    public record IccResult(
        double icc,
        int itemCount,
        int raterCount,
        boolean isValid,
        Map<UUID, Double> raterMeanDeviations,
        String diagnosticMessage
    ) {}

    /**
     * Computes ICC(3,1) for the given ratings matrix.
     *
     * @param ratingsMatrix Map of ItemId -> (Map of RaterId -> Score)
     * @return IccResult with ICC value, sample size, rater count, validity flag, and rater deviations.
     */
    public static IccResult calculateIcc31(Map<UUID, Map<UUID, Double>> ratingsMatrix) {
        if (ratingsMatrix == null || ratingsMatrix.isEmpty()) {
            return new IccResult(0.0, 0, 0, false, Collections.emptyMap(), "Empty ratings matrix");
        }

        // 1. Identify common raters across items for a balanced Two-Way ANOVA design
        Set<UUID> allRaters = new HashSet<>();
        for (Map<UUID, Double> raters : ratingsMatrix.values()) {
            if (raters != null) {
                allRaters.addAll(raters.keySet());
            }
        }

        // Filter items that have ratings from raters
        List<UUID> validItemIds = new ArrayList<>();
        // Keep raters that rated all selected items, or items with common raters
        // For a general rater pool, find items rated by at least 2 common raters
        for (Map.Entry<UUID, Map<UUID, Double>> entry : ratingsMatrix.entrySet()) {
            if (entry.getValue() != null && entry.getValue().size() >= 2) {
                validItemIds.add(entry.getKey());
            }
        }

        int n = validItemIds.size();
        if (n < 2) {
            return new IccResult(
                0.0,
                n,
                allRaters.size(),
                false,
                Collections.emptyMap(),
                "Insufficient items: at least 2 items required (found " + n + ")"
            );
        }

        // Find intersection of raters across these valid items, or evaluate on available balanced subset
        Set<UUID> commonRaters = new HashSet<>(allRaters);
        for (UUID itemId : validItemIds) {
            commonRaters.retainAll(ratingsMatrix.get(itemId).keySet());
        }

        // If common intersection is less than 2, fallback to top 2 most frequent raters for pairwise ANOVA
        List<UUID> raterList = new ArrayList<>(commonRaters);
        if (raterList.size() < 2) {
            // Count occurrences of each rater
            Map<UUID, Integer> raterCounts = new HashMap<>();
            for (UUID itemId : validItemIds) {
                for (UUID raterId : ratingsMatrix.get(itemId).keySet()) {
                    raterCounts.put(raterId, raterCounts.getOrDefault(raterId, 0) + 1);
                }
            }
            List<UUID> sortedRaters = new ArrayList<>(raterCounts.keySet());
            sortedRaters.sort((a, b) -> raterCounts.get(b).compareTo(raterCounts.get(a)));

            if (sortedRaters.size() >= 2) {
                UUID r1 = sortedRaters.get(0);
                UUID r2 = sortedRaters.get(1);
                raterList = List.of(r1, r2);
                validItemIds.removeIf(id -> !ratingsMatrix.get(id).containsKey(r1) || !ratingsMatrix.get(id).containsKey(r2));
                n = validItemIds.size();
            }
        }

        int k = raterList.size();
        if (k < 2 || n < 2) {
            return new IccResult(
                0.0,
                n,
                k,
                false,
                Collections.emptyMap(),
                "Insufficient common raters across items: at least 2 items rated by 2 common raters required"
            );
        }

        // 2. Build balanced matrix [n x k]
        double[][] data = new double[n][k];
        double grandSum = 0.0;
        int totalObservations = n * k;

        double[] rowSums = new double[n];
        double[] colSums = new double[k];

        for (int i = 0; i < n; i++) {
            UUID itemId = validItemIds.get(i);
            Map<UUID, Double> itemRatings = ratingsMatrix.get(itemId);
            for (int j = 0; j < k; j++) {
                UUID raterId = raterList.get(j);
                double val = itemRatings.get(raterId);
                data[i][j] = val;
                grandSum += val;
                rowSums[i] += val;
                colSums[j] += val;
            }
        }

        double grandMean = grandSum / totalObservations;

        // 3. Compute Sum of Squares
        // SS_Total = sum((y_ij - grandMean)^2)
        double ssTotal = 0.0;
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < k; j++) {
                double diff = data[i][j] - grandMean;
                ssTotal += diff * diff;
            }
        }

        // SS_Rows = k * sum((rowMean_i - grandMean)^2)
        double ssRows = 0.0;
        for (int i = 0; i < n; i++) {
            double rowMean = rowSums[i] / k;
            double diff = rowMean - grandMean;
            ssRows += diff * diff;
        }
        ssRows *= k;

        // SS_Columns = n * sum((colMean_j - grandMean)^2)
        double ssCols = 0.0;
        Map<UUID, Double> raterDeviations = new HashMap<>();
        for (int j = 0; j < k; j++) {
            double colMean = colSums[j] / n;
            double diff = colMean - grandMean;
            ssCols += diff * diff;
            raterDeviations.put(raterList.get(j), Math.round(diff * 1000.0) / 1000.0);
        }
        ssCols *= n;

        // SS_Error (Residual) = SS_Total - SS_Rows - SS_Columns
        double ssError = ssTotal - ssRows - ssCols;
        if (ssError < 0.0 && ssError > -1e-9) {
            ssError = 0.0; // Rounding precision correction
        }

        // 4. Mean Squares
        double dfRows = n - 1;
        double dfCols = k - 1;
        double dfError = (n - 1) * (k - 1);

        double msRows = ssRows / dfRows;
        double msCols = ssCols / dfCols;
        double msError = dfError > 0 ? (ssError / dfError) : 0.0;

        // 5. ICC(3,1) Consistency Calculation
        // ICC(3,1) = (MS_Rows - MS_Error) / (MS_Rows + (k - 1) * MS_Error)
        double denominator = msRows + (k - 1) * msError;
        if (denominator == 0.0) {
            return new IccResult(0.0, n, k, false, raterDeviations, "Zero variance or invalid denominator detected across rater pool");
        }

        double icc = (msRows - msError) / denominator;

        if (Double.isNaN(icc) || Double.isInfinite(icc)) {
            return new IccResult(0.0, n, k, false, raterDeviations, "Zero variance or invalid denominator detected across rater pool");
        }

        // Bound ICC within theoretical range [-1.0, 1.0] and format to 3 decimal places
        icc = Math.max(-1.0, Math.min(1.0, icc));
        icc = Math.round(icc * 1000.0) / 1000.0;

        String diagnostic = String.format(
            "Two-Way Mixed Consistency ICC(3,1) computed across n=%d items and k=%d raters. MS_R=%.4f, MS_C=%.4f, MS_E=%.4f",
            n, k, msRows, msCols, msError
        );

        return new IccResult(icc, n, k, true, raterDeviations, diagnostic);
    }
}
