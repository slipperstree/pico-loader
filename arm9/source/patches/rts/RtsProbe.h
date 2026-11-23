#pragma once
#include "ndsHeader.h"
#include "patches/PatchContext.h"

// Research build only. This is a CPU rendezvous diagnostic, NOT save states.
void InstallRtsProbeArm9(PatchContext& context, const nds_header_ntr_t* header, u32 imageBytes);
void InstallRtsProbeArm7(PatchContext& context, u32 cheatsLength);
extern "C" void rtsProbeMessage(const char* message);
