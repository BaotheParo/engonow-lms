package com.engonow.lms.calibration.repository;

import com.engonow.lms.calibration.domain.entity.CalibrationCorpusItem;
import com.engonow.lms.calibration.domain.entity.CalibrationReferenceScore;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface CalibrationReferenceScoreRepository extends JpaRepository<CalibrationReferenceScore, UUID> {

    @Query("SELECT s FROM CalibrationReferenceScore s WHERE s.corpusItem.id = :corpusItemId")
    List<CalibrationReferenceScore> findByCorpusItemId(@Param("corpusItemId") UUID corpusItemId);

    List<CalibrationReferenceScore> findByCorpusItem(CalibrationCorpusItem corpusItem);
}
