package com.engonow.lms.writing.domain.entity;

import com.engonow.lms.writing.domain.enums.EvaluatedBy;
import com.engonow.lms.writing.domain.feedback.WritingFeedbackDetail;
import jakarta.validation.Valid;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UuidGenerator;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

/**
 * A versioned evaluation of a writing submission. The database's partial
 * unique index guarantees that only one result per submission is current.
 */
@Entity
@Table(
    name = "writing_results",
    indexes = {
        @Index(name = "idx_writing_results_submission_id", columnList = "submission_id"),
        @Index(name = "idx_writing_results_overall_band", columnList = "overall_band")
    }
)
@Getter
@Setter
@NoArgsConstructor
public class WritingResult {

    @Id
    @GeneratedValue
    @UuidGenerator
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "submission_id",
        nullable = false,
        updatable = false,
        foreignKey = @ForeignKey(name = "fk_writing_results_submission")
    )
    private WritingSubmission submission;

    @NotNull
    @DecimalMin("0.0")
    @DecimalMax("9.0")
    @Digits(integer = 1, fraction = 1)
    @Column(name = "task_achievement_score", nullable = false, precision = 2, scale = 1)
    private BigDecimal taskAchievementScore;

    @NotNull
    @DecimalMin("0.0")
    @DecimalMax("9.0")
    @Digits(integer = 1, fraction = 1)
    @Column(name = "coherence_cohesion_score", nullable = false, precision = 2, scale = 1)
    private BigDecimal coherenceCohesionScore;

    @NotNull
    @DecimalMin("0.0")
    @DecimalMax("9.0")
    @Digits(integer = 1, fraction = 1)
    @Column(name = "lexical_resource_score", nullable = false, precision = 2, scale = 1)
    private BigDecimal lexicalResourceScore;

    @NotNull
    @DecimalMin("0.0")
    @DecimalMax("9.0")
    @Digits(integer = 1, fraction = 1)
    @Column(name = "grammatical_range_score", nullable = false, precision = 2, scale = 1)
    private BigDecimal grammaticalRangeScore;

    @NotNull
    @DecimalMin("0.0")
    @DecimalMax("9.0")
    @Digits(integer = 1, fraction = 1)
    @Column(name = "overall_band", nullable = false, precision = 2, scale = 1)
    private BigDecimal overallBand;

    @NotNull
    @Valid
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "feedback_detail", nullable = false)
    private WritingFeedbackDetail feedbackDetail;

    @NotBlank
    @Size(max = 60)
    @Column(name = "ai_model_version", nullable = false, updatable = false, length = 60)
    private String aiModelVersion;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "evaluated_by", nullable = false, updatable = false, length = 20)
    private EvaluatedBy evaluatedBy = EvaluatedBy.AI_AUTO;

    @NotNull
    @Min(1)
    @Column(name = "result_version", nullable = false, updatable = false)
    private Integer resultVersion = 1;

    @NotNull
    @Column(name = "is_current", nullable = false)
    private Boolean isCurrent = true;

    @NotNull
    @Column(name = "evaluated_at", nullable = false, updatable = false)
    private Instant evaluatedAt;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Version
    @Column(name = "version", nullable = false)
    private Long version = 0L;

    /** Marks this result as historical before its successor becomes current. */
    public void supersede() {
        isCurrent = false;
    }

    /**
     * Persistent identity equality: transient instances are never equal, and
     * an assigned database identifier remains stable across persistence states.
     */
    @Override
    public final boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof WritingResult that)) {
            return false;
        }
        return id != null && Objects.equals(id, that.id);
    }

    /** Uses a stable class-level hash until and after the identifier is assigned. */
    @Override
    public final int hashCode() {
        return getClass().hashCode();
    }
}
