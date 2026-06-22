package com.engonow.lms.entity;

import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Stores the combined Speaking Test result: AI grading (80%) + Tutor rubric (20%).
 *
 * Design notes:
 *  - Linked to MockTestBooking via @OneToOne (owning side, holds the FK).
 *  - AI Score (0-9 IELTS band): stored as DECIMAL(4,2) for precision (e.g., 6.50).
 *  - Tutor rubric scores: 4 IELTS criteria (Fluency, Lexical, Grammar, Pronunciation).
 *  - finalBand: computed and stored on save — avoids recalculation on every read.
 *  - sessionId: the opaque ID returned by the AI service in the webhook callback,
 *    used for idempotency (re-delivered webhooks with same sessionId are ignored).
 */
@Entity
@Table(name = "speaking_session_results",
       uniqueConstraints = @UniqueConstraint(
           name = "uk_session_id",
           columnNames = "session_id"
       ))
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SpeakingSessionResult extends BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * Owning side of @OneToOne — holds FK column booking_id.
     */
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "booking_id", nullable = false,
                foreignKey = @ForeignKey(name = "fk_result_booking"))
    private MockTestBooking booking;

    /**
     * Opaque session ID from the AI grading service.
     * Used to deduplicate re-delivered webhook callbacks.
     */
    @Column(name = "session_id", nullable = false, length = 100)
    private String sessionId;

    // ── AI Grading (80% weight) ───────────────────────────────────────────

    @Column(name = "ai_score", precision = 4, scale = 2)
    private BigDecimal aiScore;

    @Column(name = "ai_feedback", columnDefinition = "TEXT")
    private String aiFeedback;

    // ── Tutor Rubric (20% weight) ─────────────────────────────────────────
    // Each criterion is 0–9 IELTS band; average of 4 = tutor component score.

    @Column(name = "tutor_fluency_score", precision = 3, scale = 1)
    private BigDecimal tutorFluencyScore;

    @Column(name = "tutor_lexical_score", precision = 3, scale = 1)
    private BigDecimal tutorLexicalScore;

    @Column(name = "tutor_grammar_score", precision = 3, scale = 1)
    private BigDecimal tutorGrammarScore;

    @Column(name = "tutor_pronunciation_score", precision = 3, scale = 1)
    private BigDecimal tutorPronunciationScore;

    @Column(name = "tutor_comments", columnDefinition = "TEXT")
    private String tutorComments;

    // ── Computed Final Result ─────────────────────────────────────────────

    /**
     * finalBand = (aiScore * 0.80) + (avgTutorScore * 0.20)
     * Rounded to nearest 0.5 per IELTS band conventions.
     */
    @Column(name = "final_band", precision = 3, scale = 1)
    private BigDecimal finalBand;

    @Builder.Default
    @Column(name = "is_complete", nullable = false)
    private Boolean isComplete = false;

    // ── Business Logic ────────────────────────────────────────────────────

    /**
     * Call this once both AI and tutor scores are available to compute the final band.
     * Uses IELTS rounding: round to nearest 0.5.
     */
    public void computeFinalBand() {
        if (aiScore == null || tutorFluencyScore == null) return;

        BigDecimal avgTutor = tutorFluencyScore
            .add(tutorLexicalScore)
            .add(tutorGrammarScore)
            .add(tutorPronunciationScore)
            .divide(BigDecimal.valueOf(4), 2, RoundingMode.HALF_UP);

        BigDecimal raw = aiScore.multiply(new BigDecimal("0.80"))
            .add(avgTutor.multiply(new BigDecimal("0.20")));

        // IELTS rounding: to nearest 0.5
        this.finalBand = raw.multiply(BigDecimal.valueOf(2))
            .setScale(0, RoundingMode.HALF_UP)
            .divide(BigDecimal.valueOf(2), 1, RoundingMode.HALF_UP);

        this.isComplete = true;
    }
}
