package com.engonow.lms.calibration.repository;

import com.engonow.lms.calibration.domain.entity.CalibrationCorpusItem;
import com.engonow.lms.calibration.domain.enums.CorpusItemStatus;
import com.engonow.lms.calibration.domain.enums.DatasetSplit;
import com.engonow.lms.calibration.domain.enums.SubsystemType;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface CalibrationCorpusItemRepository extends JpaRepository<CalibrationCorpusItem, UUID> {

    List<CalibrationCorpusItem> findBySubsystemAndDatasetSplit(SubsystemType subsystem, DatasetSplit datasetSplit);

    @Query("SELECT DISTINCT c FROM CalibrationCorpusItem c LEFT JOIN FETCH c.ratings WHERE c.subsystem = :subsystem AND c.datasetSplit = :split")
    List<CalibrationCorpusItem> findWithRatingsBySubsystemAndSplit(@Param("subsystem") SubsystemType subsystem, @Param("split") DatasetSplit split);

    @Query("SELECT DISTINCT c FROM CalibrationCorpusItem c LEFT JOIN FETCH c.referenceScores WHERE c.subsystem = :subsystem AND c.datasetSplit = :split")
    List<CalibrationCorpusItem> findWithReferenceScoresBySubsystemAndSplit(@Param("subsystem") SubsystemType subsystem, @Param("split") DatasetSplit split);

    @EntityGraph(attributePaths = {"ratings", "referenceScores"})
    @Query("SELECT c FROM CalibrationCorpusItem c WHERE c.id = :id")
    Optional<CalibrationCorpusItem> findWithDetailsById(@Param("id") UUID id);

    long countByIntakeBatchId(UUID intakeBatchId);

    List<CalibrationCorpusItem> findByStatus(CorpusItemStatus status);
}
