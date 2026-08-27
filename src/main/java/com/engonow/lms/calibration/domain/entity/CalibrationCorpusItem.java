package com.engonow.lms.calibration.domain.entity;

import com.engonow.lms.calibration.domain.enums.BandStratum;
import com.engonow.lms.calibration.domain.enums.CorpusItemStatus;
import com.engonow.lms.calibration.domain.enums.DatasetSplit;
import com.engonow.lms.calibration.domain.enums.SubsystemType;
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import jakarta.validation.constraints.NotNull;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UuidGenerator;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Entity
@Table(
    name = "calibration_corpus_items",
    indexes = {
        @Index(name = "idx_calibration_items_split", columnList = "subsystem, dataset_split"),
        @Index(name = "idx_calibration_items_stratum", columnList = "target_band_stratum"),
        @Index(name = "idx_calibration_items_status", columnList = "status"),
        @Index(name = "idx_calibration_items_batch", columnList = "intake_batch_id"),
        @Index(name = "idx_calibration_items_dedup_lookup", columnList = "subsystem, task_type"),
        @Index(name = "idx_calibration_items_content_hash", columnList = "content_hash")
    }
)
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class CalibrationCorpusItem {

    @Id
    @GeneratedValue
    @UuidGenerator
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "subsystem", nullable = false, length = 20)
    private SubsystemType subsystem;

    @NotNull
    @Column(name = "task_type", nullable = false, length = 50)
    private String taskType;

    @NotNull
    @Column(name = "prompt_text", nullable = false, columnDefinition = "TEXT")
    private String promptText;

    @Column(name = "essay_text", columnDefinition = "TEXT")
    private String essayText;

    @Column(name = "source_audio_url", columnDefinition = "TEXT")
    private String sourceAudioUrl;

    @Column(name = "source_audio_duration_seconds")
    private Integer sourceAudioDurationSeconds;

    @Column(name = "source_transcript", columnDefinition = "TEXT")
    private String sourceTranscript;

    @Column(name = "calibration_hold_until")
    private Instant calibrationHoldUntil;

    @NotNull
    @Convert(converter = BandStratum.BandStratumConverter.class)
    @Column(name = "target_band_stratum", nullable = false, length = 10)
    private BandStratum targetBandStratum;

    @NotNull
    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "dataset_split", nullable = false, length = 20)
    private DatasetSplit datasetSplit = DatasetSplit.UNASSIGNED;

    @Column(name = "split_assigned_at")
    private Instant splitAssignedAt;

    @Column(name = "split_locked_at")
    private Instant splitLockedAt;

    @NotNull
    @Column(name = "intake_batch_id", nullable = false)
    private UUID intakeBatchId;

    @Column(name = "content_hash", length = 64)
    private String contentHash;

    @NotNull
    @Builder.Default
    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 40)
    private CorpusItemStatus status = CorpusItemStatus.PENDING_RATING;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    @Builder.Default
    @OneToMany(mappedBy = "corpusItem", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<CalibrationHumanRating> ratings = new ArrayList<>();

    @Builder.Default
    @OneToMany(mappedBy = "corpusItem", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<CalibrationReferenceScore> referenceScores = new ArrayList<>();

    public void addRating(CalibrationHumanRating rating) {
        if (rating != null) {
            ratings.add(rating);
            rating.setCorpusItem(this);
        }
    }

    public void removeRating(CalibrationHumanRating rating) {
        if (rating != null) {
            ratings.remove(rating);
            rating.setCorpusItem(null);
        }
    }

    public void addReferenceScore(CalibrationReferenceScore referenceScore) {
        if (referenceScore != null) {
            referenceScores.add(referenceScore);
            referenceScore.setCorpusItem(this);
        }
    }

    public void removeReferenceScore(CalibrationReferenceScore referenceScore) {
        if (referenceScore != null) {
            referenceScores.remove(referenceScore);
            referenceScore.setCorpusItem(null);
        }
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        CalibrationCorpusItem that = (CalibrationCorpusItem) o;
        return id != null && id.equals(that.id);
    }

    @Override
    public int hashCode() {
        return getClass().hashCode();
    }
}
