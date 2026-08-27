package com.engonow.lms.calibration.domain.entity;

import com.engonow.lms.calibration.domain.enums.EvaluationCriterion;
import com.engonow.lms.calibration.domain.enums.ResolutionMethod;
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
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UuidGenerator;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Entity
@Table(
    name = "calibration_reference_scores",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uq_reference_per_item_criterion",
            columnNames = {"corpus_item_id", "criterion"}
        )
    },
    indexes = {
        @Index(name = "idx_calibration_ref_scores_item", columnList = "corpus_item_id")
    }
)
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CalibrationReferenceScore {

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
        foreignKey = @ForeignKey(name = "fk_calibration_ref_scores_item")
    )
    private CalibrationCorpusItem corpusItem;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "criterion", nullable = false, length = 40)
    private EvaluationCriterion criterion;

    @NotNull
    @Column(name = "reference_band", nullable = false, precision = 2, scale = 1)
    private BigDecimal referenceBand;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "resolution_method", nullable = false, length = 30)
    private ResolutionMethod resolutionMethod;

    @NotNull
    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "contributing_rating_ids", nullable = false)
    private List<UUID> contributingRatingIds;

    @Column(name = "icc_at_resolution", precision = 4, scale = 3)
    private BigDecimal iccAtResolution;

    @NotNull
    @Builder.Default
    @Column(name = "discordant", nullable = false)
    private Boolean discordant = false;

    @Column(name = "adjudicator_id")
    private UUID adjudicatorId;

    @CreationTimestamp
    @Column(name = "resolved_at", nullable = false, updatable = false)
    private Instant resolvedAt;

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        CalibrationReferenceScore that = (CalibrationReferenceScore) o;
        return id != null && id.equals(that.id);
    }

    @Override
    public int hashCode() {
        return getClass().hashCode();
    }
}
