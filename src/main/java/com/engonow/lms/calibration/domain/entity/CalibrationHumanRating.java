package com.engonow.lms.calibration.domain.entity;

import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.engonow.lms.calibration.domain.enums.RaterCredentialLevel;
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
import jakarta.persistence.UniqueConstraint;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UuidGenerator;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(
    name = "calibration_human_ratings",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uq_rating_per_rater_criterion",
            columnNames = {"corpus_item_id", "rater_id", "criterion"}
        )
    },
    indexes = {
        @Index(name = "idx_calibration_ratings_item", columnList = "corpus_item_id")
    }
)
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CalibrationHumanRating {

    @Id
    @GeneratedValue
    @UuidGenerator
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "corpus_item_id",
        nullable = false,
        foreignKey = @ForeignKey(name = "fk_calibration_ratings_item")
    )
    private CalibrationCorpusItem corpusItem;

    @NotNull
    @Column(name = "rater_id", nullable = false)
    private UUID raterId;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "rater_credential_level", nullable = false, length = 30)
    private RaterCredentialLevel raterCredentialLevel;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "criterion", nullable = false, length = 40)
    private EvaluationCriterion criterion;

    @NotNull
    @Column(name = "band_score", nullable = false, precision = 2, scale = 1)
    private BigDecimal bandScore;

    @NotNull
    @Builder.Default
    @Column(name = "transcript_flagged_incorrect", nullable = false)
    private Boolean transcriptFlaggedIncorrect = false;

    @Column(name = "rating_notes", columnDefinition = "TEXT")
    private String ratingNotes;

    @CreationTimestamp
    @Column(name = "rated_at", nullable = false, updatable = false)
    private Instant ratedAt;

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        CalibrationHumanRating that = (CalibrationHumanRating) o;
        return id != null && id.equals(that.id);
    }

    @Override
    public int hashCode() {
        return getClass().hashCode();
    }
}
