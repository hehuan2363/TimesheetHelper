document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("entry-form");
  if (!form) {
    return;
  }

  const entryIdInput = document.getElementById("entry-id");
  const entryDateInput = document.getElementById("entry-date");
  const startTimeInput = document.getElementById("start-time");
  const endTimeInput = document.getElementById("end-time");
  const chargeCodeInput = document.getElementById("charge-code");
  const activityInput = document.getElementById("activity-text");
  const submitButton = document.getElementById("entry-submit");
  const cancelButton = document.getElementById("entry-cancel");
  const addEntryButton = document.getElementById("add-entry-button");
  const modalBackdrop = document.getElementById("entry-modal");
  const modalClose = document.getElementById("entry-close");
  const modalTitle = document.getElementById("modal-title");
  const calendarGrid = document.querySelector(".calendar-grid");
  const notesModal = document.getElementById("notes-modal");
  const notesTitle = document.getElementById("notes-title");
  const notesContent = document.getElementById("notes-content");
  const notesClose = document.getElementById("notes-close");
  const toast = document.getElementById("toast");

  const MAX_MINUTE = 23 * 60 + 59;
  const DEFAULT_START_MINUTE = 9 * 60;
  let slotInterval = 30;

  const minutesToTime = (minuteValue) => {
    const clamped = Math.min(Math.max(0, Math.round(minuteValue)), MAX_MINUTE);
    const hours = Math.floor(clamped / 60);
    const minutes = clamped % 60;
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
  };

  const clearForm = () => {
    form.reset();
    if (entryIdInput) {
      entryIdInput.value = "";
    }
  };

  const setFormMode = (mode) => {
    if (modalTitle) {
      modalTitle.textContent = mode === "edit" ? "Edit Entry" : "New Entry";
    }
    if (submitButton) {
      submitButton.textContent = mode === "edit" ? "Update Entry" : "Save Entry";
      submitButton.disabled = false;
    }
  };

  const openModal = (mode) => {
    if (!modalBackdrop) {
      return;
    }
    modalBackdrop.hidden = false;
    modalBackdrop.removeAttribute("hidden");
    document.body.classList.add("modal-open");
    setFormMode(mode);
  };

  const closeModal = ({ resetFormState = true } = {}) => {
    if (!modalBackdrop) {
      return;
    }
    modalBackdrop.hidden = true;
    modalBackdrop.setAttribute("hidden", "hidden");
    document.body.classList.remove("modal-open");
    if (notesModal && !notesModal.hidden) {
      document.body.classList.add("modal-open");
    }
    if (resetFormState) {
      clearForm();
      setFormMode("new");
    }
  };

  const fillTimeRange = (startMinute, endMinute) => {
    if (startTimeInput) {
      startTimeInput.value = minutesToTime(startMinute);
    }
    if (endTimeInput) {
      const boundedEnd = Math.max(startMinute + 1, Math.min(endMinute, MAX_MINUTE));
      endTimeInput.value = minutesToTime(boundedEnd);
    }
  };

  const startNewEntry = (dateValue, startMinute, endMinute) => {
    const fallbackDate =
      entryDateInput && entryDateInput.options.length > 0
        ? entryDateInput.options[0].value
        : undefined;
    clearForm();
    if (entryDateInput) {
      entryDateInput.value = dateValue || fallbackDate || "";
    }
    fillTimeRange(startMinute, endMinute);
    if (activityInput) {
      activityInput.value = "";
    }
    openModal("new");
    if (chargeCodeInput && !chargeCodeInput.value) {
      chargeCodeInput.focus();
    } else if (activityInput) {
      activityInput.focus();
    }
  };

  const startEditEntry = (button) => {
    const { entryId, entryDate, startTime, endTime, chargeCodeId, activityText } =
      button.dataset;
    clearForm();
    if (entryIdInput) {
      entryIdInput.value = entryId || "";
    }
    if (entryDateInput && entryDate) {
      entryDateInput.value = entryDate;
    }
    if (startTimeInput && startTime) {
      startTimeInput.value = startTime;
    }
    if (endTimeInput && endTime) {
      endTimeInput.value = endTime;
    }
    if (chargeCodeInput && chargeCodeId) {
      chargeCodeInput.value = chargeCodeId;
    }
    if (activityInput && typeof activityText === "string") {
      activityInput.value = activityText;
    }
    openModal("edit");
    if (activityInput) {
      activityInput.focus();
    }
  };

  document.querySelectorAll(".edit-entry").forEach((button) => {
    button.addEventListener("click", () => startEditEntry(button));
  });

  if (cancelButton) {
    cancelButton.addEventListener("click", (event) => {
      event.preventDefault();
      closeModal();
    });
  }

  if (modalClose) {
    modalClose.addEventListener("click", () => closeModal());
  }

  if (modalBackdrop) {
    modalBackdrop.addEventListener("click", (event) => {
      if (event.target === modalBackdrop) {
        closeModal();
      }
    });
  }

  form.addEventListener("submit", () => {
    if (submitButton) {
      submitButton.disabled = true;
    }
  });

  // Ensure the modal starts closed in case browser restores prior state.
  closeModal({ resetFormState: false });

  if (addEntryButton) {
    addEntryButton.addEventListener("click", () => {
      if (addEntryButton.disabled) {
        return;
      }
      const selectedDate = entryDateInput ? entryDateInput.value : undefined;
      startNewEntry(
        selectedDate,
        DEFAULT_START_MINUTE,
        DEFAULT_START_MINUTE + slotInterval
      );
    });
  }

  const showToast = (message) => {
    if (!toast) {
      return;
    }
    toast.textContent = message;
    toast.hidden = false;
    setTimeout(() => {
      toast.hidden = true;
    }, 2000);
  };

  if (calendarGrid) {
    const parsedInterval = parseInt(calendarGrid.dataset.interval, 10);
    if (Number.isFinite(parsedInterval) && parsedInterval > 0) {
      slotInterval = parsedInterval;
    }

    const slots = Array.from(calendarGrid.querySelectorAll(".time-slot"));
    const slotsByDay = new Map();

    slots.forEach((slot) => {
      const day = slot.dataset.date;
      if (!day) {
        return;
      }
      if (!slotsByDay.has(day)) {
        slotsByDay.set(day, []);
      }
      slotsByDay.get(day).push(slot);
    });

    let selectionState = null;

    const clearHighlights = () => {
      slots.forEach((slot) => slot.classList.remove("is-selecting"));
    };

    const updateHighlights = () => {
      if (!selectionState) {
        return;
      }
      const daySlots = slotsByDay.get(selectionState.day) || [];
      const startMinute = Math.min(selectionState.anchor, selectionState.current);
      const endMinute = Math.max(selectionState.anchor, selectionState.current) + slotInterval;
      daySlots.forEach((slot) => {
        const minute = parseInt(slot.dataset.minute, 10);
        if (!Number.isFinite(minute)) {
          return;
        }
        const slotEnd = minute + slotInterval;
        if (slotEnd > startMinute && minute < endMinute) {
          slot.classList.add("is-selecting");
        } else {
          slot.classList.remove("is-selecting");
        }
      });
    };

    const startSelection = (slot, minute) => {
      clearHighlights();
      selectionState = {
        day: slot.dataset.date,
        anchor: minute,
        current: minute,
      };
      document.body.classList.add("calendar-selecting");
      updateHighlights();
    };

    const endSelection = (finalize = false) => {
      if (!selectionState) {
        document.body.classList.remove("calendar-selecting");
        return;
      }
      const { day, anchor, current } = selectionState;
      clearHighlights();
      selectionState = null;
      document.body.classList.remove("calendar-selecting");

      if (!finalize) {
        return;
      }

      const startMinute = Math.min(anchor, current);
      let endMinute = Math.max(anchor, current) + slotInterval;
      endMinute = Math.max(startMinute + slotInterval, endMinute);
      endMinute = Math.min(endMinute, MAX_MINUTE);
      startNewEntry(day, startMinute, endMinute);
    };

    slots.forEach((slot) => {
      slot.addEventListener("mousedown", (event) => {
        if (event.button !== 0) {
          return;
        }
        event.preventDefault();
        const minute = parseInt(slot.dataset.minute, 10);
        if (!slot.dataset.date || !Number.isFinite(minute)) {
          return;
        }
        const selection = window.getSelection();
        if (selection && selection.removeAllRanges) {
          selection.removeAllRanges();
        }
        startSelection(slot, minute);
      });

      slot.addEventListener("mouseenter", () => {
        if (!selectionState) {
          return;
        }
        if (slot.dataset.date !== selectionState.day) {
          return;
        }
        const minute = parseInt(slot.dataset.minute, 10);
        if (!Number.isFinite(minute)) {
          return;
        }
        selectionState.current = minute;
        updateHighlights();
      });

      slot.addEventListener("dragstart", (event) => {
        event.preventDefault();
      });
    });

    window.addEventListener("mouseup", () => endSelection(true));
    window.addEventListener("blur", () => endSelection(false));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (notesModal && !notesModal.hidden) {
          closeNotesModal();
          if (!modalBackdrop || modalBackdrop.hidden) {
            return;
          }
        }
        if (modalBackdrop && !modalBackdrop.hidden) {
          closeModal();
          return;
        }
        endSelection(false);
      }
    });
  } else {
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (notesModal && !notesModal.hidden) {
          closeNotesModal();
          if (!modalBackdrop || modalBackdrop.hidden) {
            return;
          }
        }
        if (modalBackdrop && !modalBackdrop.hidden) {
          closeModal();
        }
      }
    });
  }

  const copyToClipboard = async (text) => {
    if (!text) return false;
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (error) {
        console.error("Clipboard write failed", error);
      }
    }

    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const success = document.execCommand("copy");
      document.body.removeChild(textarea);
      return success;
    } catch (fallbackError) {
      console.error("Fallback copy failed", fallbackError);
      return false;
    }
  };

  const openNotesModal = (title, details) => {
    if (!notesModal || !notesContent) {
      return;
    }
    notesContent.innerHTML = "";
    if (notesTitle) {
      notesTitle.textContent = title || "Activity Notes";
    }
    if (!details || details.length === 0) {
      const div = document.createElement("div");
      div.className = "empty";
      div.textContent = "No activity notes recorded.";
      notesContent.appendChild(div);
    } else {
      details.forEach((item, index) => {
        const div = document.createElement("div");
        const label = `${index + 1}.`;
        const range = item.start_time && item.end_time ? `${item.start_time} – ${item.end_time}` : "";
        const text = item.activity_text || "";
        div.textContent = [label, range, text].filter(Boolean).join("  ");
        notesContent.appendChild(div);
      });
    }
    notesModal.hidden = false;
    notesModal.removeAttribute("hidden");
    document.body.classList.add("modal-open");
  };

  const closeNotesModal = () => {
    if (!notesModal) {
      return;
    }
    notesModal.hidden = true;
    notesModal.setAttribute("hidden", "hidden");
    if (!modalBackdrop || modalBackdrop.hidden) {
      document.body.classList.remove("modal-open");
    }
  };

  document.querySelectorAll(".copy-cell").forEach((button) => {
    button.addEventListener("click", async () => {
      const raw = button.dataset.copyComments || "";
      let lines = [];
      if (raw) {
        try {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed)) {
            lines = parsed.map((line) => String(line).trim()).filter(Boolean);
          }
        } catch (error) {
          lines = raw
            .split("|")
            .map((line) => line.trim())
            .filter(Boolean);
        }
      }
      const text = lines.join("\n");
      if (!text) {
        showToast("No activity to copy");
        return;
      }
      const success = await copyToClipboard(text);
      showToast(success ? "Activity copied" : "Copy unavailable");
    });
  });

  document.querySelectorAll(".comment-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      if (!notesModal) {
        return;
      }
      const comments = button.dataset.comments || "";
      const detailsRaw = button.dataset.details || "";
      let lines = [];
      if (comments) {
        try {
          const parsed = JSON.parse(comments);
          if (Array.isArray(parsed)) {
            lines = parsed.map((line) => String(line).trim()).filter(Boolean);
          }
        } catch (error) {
          lines = comments
            .split("|")
            .map((line) => line.trim())
            .filter(Boolean);
        }
      }
      let details = [];
      if (detailsRaw) {
        try {
          const parsedDetails = JSON.parse(detailsRaw);
          if (Array.isArray(parsedDetails)) {
            details = parsedDetails.map((item) => ({
              start_time: item.start_time,
              end_time: item.end_time,
              activity_text: item.activity_text,
            }));
          }
        } catch (error) {
          details = lines.map((text) => ({ start_time: "", end_time: "", activity_text: text }));
        }
      }
      const dayLabel = button.dataset.dayLabel || "";
      const chargeLabel = button.dataset.chargeLabel || "";
      const modalHeader = [chargeLabel, dayLabel].filter(Boolean).join(" · ") || "Activity Notes";
      openNotesModal(modalHeader, details.length ? details : lines);
    });
  });

  if (notesClose) {
    notesClose.addEventListener("click", () => closeNotesModal());
  }

  if (notesModal) {
    notesModal.addEventListener("click", (event) => {
      if (event.target === notesModal) {
        closeNotesModal();
      }
    });
  }
});
