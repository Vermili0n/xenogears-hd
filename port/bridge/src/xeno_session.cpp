#include "xeno_session.h"
#include "xeno_discs.h"
#include "xeno_translation.h"

#include "Foundation/Crc32.h"
#include "Foundation/LittleEndian.h"
#include "Foundation/Sha1.h"
#include "Battle/BattleCombatant.h"
#include "Battle/BattleContext.h"
#include "Battle/BattleEnd.h"
#include "Battle/BattleResult.h"
#include "Battle/BattleRuntime.h"
#include "Battle/Show/BattleObjectsFrame.h"
#include "Battle/Show/BattlePresentation.h"
#include "Battle/Show/BattleShowFrame.h"
#include "Battle/Show/BattleShowObjects.h"
#include "Battle/Show/BattleShowTransition.h"
#include "Battling/BattlingDrawing.h"
#include "Battling/BattlingFight.h"
#include "Field/EventInstructionSet.h"
#include "Field/FieldBackdrop.h"
#include "Field/FieldGearDrawing.h"
#include "Field/FieldSpriteModels.h"
#include "Field/FieldMap.h"
#include "Game/BattleGameFiles.h"
#include "Game/BattleGameProgram.h"
#include "Game/BattlingGameProgram.h"
#include "Game/BootNotice.h"
#include "Game/CharacterSkills.h"
#include "Game/ChapterCardDrawing.h"
#include "Game/FieldMovie.h"
#include "Game/MovieProgram.h"
#include "Graphics/Mdec.h"
#include "Menu/MenuGameMenus.h"
#include "Menu/MenuProgram.h"
#include "Menu/MenuResources.h"
#include "Gears/GearCloth.h"
#include "Gears/GearPackets.h"
#include "Graphics/AffineBlend.h"
#include "Graphics/Texture.h"
#include "Menu/MenuDrawing.h"
#include "Field/FieldSprites.h"
#include "Game/FieldProgram.h"
#include "Graphics/Sprite.h"
#include "Graphics/SpriteDrawing.h"
#include "Game/GearPartTables.h"
#include "Game/KernelState.h"
#include "Game/OriginalSave.h"
#include "Game/SaveState.h"
#include "Game/SaveStore.h"
#include "Game/WorldMapProgram.h"
#include "Game/SaveLoad.h"
#include "Game/GameLoop.h"
#include "Game/GamePace.h"
#include "Game/GameSession.h"
#include "Game/GameState.h"
// The core's own layout of the game state's records (a header of its private sources, read only): where a character's and a
// gear's record lie, as every program of the core reads them.
#include "Game/GameStateLayout.h"
#include "Game/PsxRandom.h"
#include "Graphics/BeetleTextureNames.h"
#include "Graphics/TextureRegion.h"
#include "Media/CdImage.h"
#include "Media/DiscAssets.h"
#include "Media/DiscIdentification.h"
#include "Media/DiscModFiles.h"
#include "Media/GameFileIndex.h"
#include "Media/GameLibrary.h"
#include "Media/Iso9660.h"
#include "Media/PsxExecutable.h"
#include "Menu/MenuSaveCards.h"
#include "Menu/MenuStoreHint.h"
#include "Sound/GameSoundSession.h"
#include "Text/MesFontSheet.h"
#include "Text/MesResident.h"
#include "Text/MesText.h"
#include "Text/MessageTable.h"
#include "Sound/UnheardGameSound.h"
#include "Support/NewGameParty.h"
#include "Timing/PsxTiming.h"
#include "Timing/TickClock.h"

#include <algorithm>
#include <bit>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <map>
#include <optional>
#include <set>
#include <string_view>
#include <tuple>
#include <unordered_map>
#include <unordered_set>

using namespace Weltall;

namespace Xeno
{
	namespace
	{
		constexpr float Untextured = 3.0f;
		constexpr float FlagRaw = 1.0f;
		constexpr float FlagSemi = 2.0f;
		constexpr float FlagSemiAll = 4.0f;
		/** The texels wrap in a texture window (C2: the window's offset, then the bits of a texel coordinate it replaces). */
		constexpr float FlagWindow = 8.0f;

		/** A corner as the shaders take it. */
		struct FCorner
		{
			std::array<float, 3> Pos{};
			std::array<uint8_t, 3> Color{128, 128, 128};
			float U = 0.0f;
			float V = 0.0f;
		};

		/** What a whole primitive shares. */
		struct FLook
		{
			float PageX = 0.0f, PageY = 0.0f, Depth = Untextured, Flags = 0.0f;
			float ClutX = 0.0f, ClutY = 0.0f, Spans = 0.0f;
			std::array<float, 4> Clamp{-1.0f, -1.0f, -1.0f, -1.0f};
			/** Its place in a battle frame's drawing order (0: none, the field's). */
			float Order = 0.0f;
			/** On the 2D layer, the drawing area's rectangle of screen pixels it is drawn inside (left, top, right, bottom); -1: none. */
			std::array<float, 4> Area{-1.0f, -1.0f, -1.0f, -1.0f};
		};

		/** Where a primitive's texels lie in a picture of the pack: picture u = (texel u + AddU) / Wide, likewise v. */
		struct FHdHit
		{
			enum : uint8 { None, Upload, Rect } Kind = None;
			std::string Texture;
			float AddU = 0.0f, AddV = 0.0f, Wide = 1.0f, High = 1.0f;
			/**
			 * A picture found by content (AliasName, RegionAlias): the texels the game draws there and the picture's original
			 * lacked (u | v << 16 in the picture's texels), drawn from VRAM under the picture so it shows no holes there.
			 */
			std::vector<uint32> Added;
		};

		void Push(FMeshBuffers& Mesh, const FCorner& Corner, const std::array<float, 3>& Normal, const FLook& Look)
		{
			Mesh.Pos.insert(Mesh.Pos.end(), Corner.Pos.begin(), Corner.Pos.end());
			Mesh.Normal.insert(Mesh.Normal.end(), Normal.begin(), Normal.end());
			Mesh.Color.insert(Mesh.Color.end(), {Corner.Color[0] / 255.0f, Corner.Color[1] / 255.0f, Corner.Color[2] / 255.0f, 1.0f});
			Mesh.Uv.insert(Mesh.Uv.end(), {Corner.U, Corner.V});
			Mesh.C0.insert(Mesh.C0.end(), {Look.PageX, Look.PageY, Look.Depth, Look.Flags});
			Mesh.C1.insert(Mesh.C1.end(), {Look.ClutX, Look.ClutY, Look.Spans, Look.Order});
			Mesh.C2.insert(Mesh.C2.end(), Look.Clamp.begin(), Look.Clamp.end());
			Mesh.C3.insert(Mesh.C3.end(), Look.Area.begin(), Look.Area.end());
		}

		std::array<float, 3> FaceNormal(const FCorner& A, const FCorner& B, const FCorner& C)
		{
			const float Ux = B.Pos[0] - A.Pos[0], Uy = B.Pos[1] - A.Pos[1], Uz = B.Pos[2] - A.Pos[2];
			const float Vx = C.Pos[0] - A.Pos[0], Vy = C.Pos[1] - A.Pos[1], Vz = C.Pos[2] - A.Pos[2];
			std::array<float, 3> N{Uy * Vz - Uz * Vy, Uz * Vx - Ux * Vz, Ux * Vy - Uy * Vx};
			const float Length = std::sqrt(N[0] * N[0] + N[1] * N[1] + N[2] * N[2]);
			if (Length < 1e-12f)
			{
				return {0.0f, 0.0f, 1.0f};
			}
			return {N[0] / Length, N[1] / Length, N[2] / Length};
		}

		/**
		 * A triangle, or a quad as the GPU draws it: (0, 1, 2) and (1, 3, 2). Each triangle gets its face's normal, or
		 * Facing (a quad kept facing the screen).
		 */
		void PushPrimitive(FMeshBuffers& Mesh, const std::array<FCorner, 4>& Corners, int Count, const FLook& Look, const std::array<float, 3>* Facing = nullptr)
		{
			const auto Triangle = [&](int A, int B, int C) {
				const std::array<float, 3> Normal = Facing != nullptr ? *Facing : FaceNormal(Corners[A], Corners[B], Corners[C]);
				for (int Index : {A, B, C})
				{
					Push(Mesh, Corners[static_cast<std::size_t>(Index)], Normal, Look);
				}
			};
			Triangle(0, 1, 2);
			if (Count == 4)
			{
				Triangle(1, 3, 2);
			}
		}

		/** View space (x right, y down, z forward) to Godot's (y up, -z forward), scaled. */
		std::array<float, 3> ToGodot(const std::array<float, 3>& View)
		{
			return {View[0] * ViewScale, -View[1] * ViewScale, -View[2] * ViewScale};
		}

		std::array<float, 3> Apply(const FAffine& Affine, float X, float Y, float Z)
		{
			std::array<float, 3> Out{};
			for (std::size_t Row = 0; Row < 3; ++Row)
			{
				Out[Row] = Affine.M[Row][0] * X + Affine.M[Row][1] * Y + Affine.M[Row][2] * Z + Affine.T[Row];
			}
			return Out;
		}

		EBlend BlendOf(EBlendMode Mode)
		{
			return static_cast<EBlend>(1 + static_cast<int>(Mode));
		}

		void SetPage(FLook& Look, const FTexturePage& Page, const FClutPosition& Clut)
		{
			Look.PageX = static_cast<float>(Page.X);
			Look.PageY = static_cast<float>(Page.Y);
			Look.Depth = static_cast<float>(static_cast<int>(Page.Depth));
			Look.ClutX = static_cast<float>(Clut.X);
			Look.ClutY = static_cast<float>(Clut.Y);
		}

		std::array<uint8_t, 3> ColorOf(const FMdlColor& Color)
		{
			return {Color.R, Color.G, Color.B};
		}

		int TexelsPerUnit(ETextureDepth Depth)
		{
			return Depth == ETextureDepth::Indexed4 ? 4 : Depth == ETextureDepth::Indexed8 ? 2 : 1;
		}

		/** The colour a texel of a page shows through its CLUT (a 15-bit page's own unit); U and V count from the page's corner. */
		uint16 TexelColor(const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, int U, int V)
		{
			const int Per = TexelsPerUnit(Page.Depth);
			const int Column = Page.X * Per + U;
			const int Unit = Column >= 0 ? Column / Per : -((-Column + Per - 1) / Per);
			const int Within = Column - Unit * Per;
			const uint16 Word = Vram.TexelAt(Unit, Page.Y + V);
			if (Page.Depth == ETextureDepth::Indexed4)
			{
				return Vram.TexelAt(Clut.X + (Word >> (Within * 4) & 15), Clut.Y);
			}
			if (Page.Depth == ETextureDepth::Indexed8)
			{
				return Vram.TexelAt(Clut.X + (Word >> (Within * 8) & 255), Clut.Y);
			}
			return Word;
		}

		uint64 PackKey(uint32 Upload, uint32 Palette)
		{
			return static_cast<uint64>(Upload) << 32 | Palette;
		}

		/** Surfaces by blend mode and picture: merged wherever they are (the scene), or only one after another (the 2D layer's order). */
		class FCollector
		{
		public:
			FCollector(std::vector<FSurface>& InOut, bool bInRuns) : Out(InOut), bRuns(bInRuns) { Out.clear(); }

			FMeshBuffers& Get(EBlend Blend, const std::string& Texture)
			{
				// VRAM's texels come from the VRAM pushed now; a picture's surface does not sample VRAM.
				const int From = Texture.empty() ? Vram : SceneVram;
				if (bRuns)
				{
					if (Out.empty() || Out.back().Blend != Blend || Out.back().Texture != Texture || Out.back().Vram != From || Out.back().bUnlit != bUnlit
						|| Out.back().Area != Area)
					{
						Out.push_back({Blend, Texture, {}, From, bUnlit, Area});
					}
					return Out.back().Mesh;
				}
				const std::string Key = std::to_string(static_cast<int>(Blend)) + '|' + std::to_string(From) + (bUnlit ? "|u|" : "|l|") + Texture;
				const auto Found = Index.find(Key);
				if (Found != Index.end())
				{
					return Out[Found->second].Mesh;
				}
				Index.emplace(Key, Out.size());
				Out.push_back({Blend, Texture, {}, From, bUnlit});
				return Out.back().Mesh;
			}

			/** Which VRAM (EVramSource) the primitives pushed from now on sample. */
			int Vram = SceneVram;
			/** The primitives pushed from now on are the game's own picture, unlit and behind everything (FSurface::bUnlit). */
			bool bUnlit = false;
			/** The drawing area of the 2D layer's primitives pushed from now on (FSurface::Area; -1: none). */
			std::array<float, 4> Area{-1.0f, -1.0f, -1.0f, -1.0f};

		private:
			std::vector<FSurface>& Out;
			bool bRuns = false;
			std::unordered_map<std::string, std::size_t> Index;
		};

		/** Whether two triangles on the screen overlap by more than Sliver across every separating direction (touching edges do not). */
		bool TrianglesOverlap(const std::array<std::array<float, 2>, 3>& A, const std::array<std::array<float, 2>, 3>& B, float Sliver)
		{
			for (const auto* Edges : {&A, &B})
			{
				for (std::size_t Edge = 0; Edge < 3; ++Edge)
				{
					const std::array<float, 2>& From = (*Edges)[Edge];
					const std::array<float, 2>& To = (*Edges)[(Edge + 1) % 3];
					float Ax = To[1] - From[1], Ay = From[0] - To[0];
					const float Length = std::sqrt(Ax * Ax + Ay * Ay);
					if (Length <= 0.0f)
					{
						continue;
					}
					Ax /= Length;
					Ay /= Length;
					float MinA = 1e30f, MaxA = -1e30f, MinB = 1e30f, MaxB = -1e30f;
					for (std::size_t Corner = 0; Corner < 3; ++Corner)
					{
						const float OnA = A[Corner][0] * Ax + A[Corner][1] * Ay, OnB = B[Corner][0] * Ax + B[Corner][1] * Ay;
						MinA = std::min(MinA, OnA);
						MaxA = std::max(MaxA, OnA);
						MinB = std::min(MinB, OnB);
						MaxB = std::max(MaxB, OnB);
					}
					if (MaxA < MinB + Sliver || MaxB < MinA + Sliver)
					{
						return false;
					}
				}
			}
			return true;
		}

		/**
		 * FieldLaying (BuildWorld): the PS1 draws the field's scene in its order with no depth buffer, so a polygon lying on
		 * one drawn before it (a picture on a wall, a rug on a floor) covers it wholly; through a depth buffer the two fight
		 * along a jagged line where their planes cross. For each drawn polygon in the frame's order (Order), Scale gets the
		 * share of its distance from the eye at which its corners are drawn (scaled toward the eye: the same pixels on the
		 * screen) so that it lies just before every polygon drawn earlier that it lies on: planes within 8 degrees, each of
		 * its corners within 2 % of its distance from that one's (laid) plane, the two overlapping on the screen by more than a
		 * sliver (a pixel of the original's screen; neighbours meeting along an edge do not). 1: none under it.
		 */
		void LayScenery(const std::vector<uint32>& Order, const std::vector<std::array<std::array<float, 3>, 4>>& Corners, const std::vector<uint32>& Counts,
			std::vector<float>& Scale)
		{
			constexpr float Parallel = 0.990f;
			constexpr float Coplanar = 0.02f;
			constexpr float Before = 0.001f;
			constexpr float Sliver = 1.0f / 512.0f;
			static constexpr float Cell = 0.025f;
			static constexpr float Reach = 2.0f;
			static constexpr int32_t Across = static_cast<int32_t>(2.0f * Reach / Cell) + 1;
			struct FLaid
			{
				std::array<float, 3> Normal{};
				float Distance = 0.0f;
				std::array<std::array<float, 2>, 4> Screen{};
				/** Its box on the screen: left, top, right, bottom. */
				std::array<float, 4> Box{};
				uint32 Count = 0;
			};
			std::vector<FLaid> Planes(Corners.size());
			std::vector<uint32> Seen(Corners.size(), 0);
			uint32 Stamp = 0;
			// The screen (from -Reach to Reach both ways, as seen from the eye at distance 1) in cells, each listing the polygons laid so far over it;
			// kept between frames for its storage.
			static thread_local std::vector<std::vector<uint32>> Cells;
			Cells.resize(static_cast<std::size_t>(Across * Across));
			for (std::vector<uint32>& Listed : Cells)
			{
				Listed.clear();
			}
			static constexpr int32_t LargeCells = 1024;
			std::vector<uint32> Large;
			std::vector<uint32> Done;
			const auto CellOf = [](float At) { return std::min(static_cast<int32_t>(std::floor((std::clamp(At, -Reach, Reach) + Reach) / Cell)), Across - 1); };
			const auto Triangles = [](const FLaid& Laid, std::size_t Which) {
				return Which == 0 ? std::array<std::array<float, 2>, 3>{Laid.Screen[0], Laid.Screen[1], Laid.Screen[2]}
								  : std::array<std::array<float, 2>, 3>{Laid.Screen[1], Laid.Screen[3], Laid.Screen[2]};
			};
			for (const uint32 Number : Order)
			{
				if (Number >= Corners.size() || (Counts[Number] != 3 && Counts[Number] != 4))
				{
					continue;
				}
				const std::array<std::array<float, 3>, 4>& At = Corners[Number];
				FLaid Laid;
				Laid.Count = Counts[Number];
				bool bInFront = true;
				float Left = 1e30f, Right = -1e30f, Top = 1e30f, Bottom = -1e30f;
				for (std::size_t Corner = 0; Corner < Laid.Count; ++Corner)
				{
					if (At[Corner][2] < 1.0f)
					{
						bInFront = false;
						break;
					}
					Laid.Screen[Corner] = {At[Corner][0] / At[Corner][2], At[Corner][1] / At[Corner][2]};
					Left = std::min(Left, Laid.Screen[Corner][0]);
					Right = std::max(Right, Laid.Screen[Corner][0]);
					Top = std::min(Top, Laid.Screen[Corner][1]);
					Bottom = std::max(Bottom, Laid.Screen[Corner][1]);
				}
				const std::array<float, 3> U{At[1][0] - At[0][0], At[1][1] - At[0][1], At[1][2] - At[0][2]};
				const std::array<float, 3> V{At[2][0] - At[0][0], At[2][1] - At[0][1], At[2][2] - At[0][2]};
				std::array<float, 3> N{U[1] * V[2] - U[2] * V[1], U[2] * V[0] - U[0] * V[2], U[0] * V[1] - U[1] * V[0]};
				const float Length = std::sqrt(N[0] * N[0] + N[1] * N[1] + N[2] * N[2]);
				if (!bInFront || Length <= 1e-6f || Right < -Reach || Left > Reach || Bottom < -Reach || Top > Reach)
				{
					continue;
				}
				for (float& Axis : N)
				{
					Axis /= Length;
				}
				Laid.Normal = N;
				Laid.Box = {Left, Top, Right, Bottom};
				Laid.Distance = N[0] * At[0][0] + N[1] * At[0][1] + N[2] * At[0][2];
				// The polygons drawn before it that it lies on: the farthest it must come forward is the nearest of their planes.
				float Factor = 1.0f;
				++Stamp;
				const int32_t X0 = CellOf(Left), X1 = CellOf(Right), Y0 = CellOf(Top), Y1 = CellOf(Bottom);
				const auto Consider = [&](uint32 Under)
				{
					if (Seen[Under] == Stamp)
					{
						return;
					}
					Seen[Under] = Stamp;
					const FLaid& Base = Planes[Under];
					if (Base.Box[2] < Left + Sliver || Right < Base.Box[0] + Sliver || Base.Box[3] < Top + Sliver || Bottom < Base.Box[1] + Sliver)
					{
						return;
					}
					if (std::abs(Base.Normal[0] * N[0] + Base.Normal[1] * N[1] + Base.Normal[2] * N[2]) < Parallel)
					{
						return;
					}
					float Needed = 1.0f;
					for (std::size_t Corner = 0; Corner < Laid.Count; ++Corner)
					{
						const float Along = Base.Normal[0] * At[Corner][0] + Base.Normal[1] * At[Corner][1] + Base.Normal[2] * At[Corner][2];
						if (std::abs(Along - Base.Distance) > Coplanar * At[Corner][2] || std::abs(Along) <= 1e-6f)
						{
							return;
						}
						// Where this corner's line of sight meets the plane under it, as a share of the corner's distance.
						Needed = std::min(Needed, Base.Distance / Along);
					}
					// Neighbours in one plane meeting along an edge (two corners in common: a floor's or a wall's tiles) do not lie on
					// each other; most of the candidates are these.
					int Shared = 0;
					for (std::size_t Mine = 0; Mine < Laid.Count; ++Mine)
					{
						for (std::size_t Theirs = 0; Theirs < Base.Count; ++Theirs)
						{
							Shared += std::abs(Laid.Screen[Mine][0] - Base.Screen[Theirs][0]) < 1e-5f && std::abs(Laid.Screen[Mine][1] - Base.Screen[Theirs][1]) < 1e-5f ? 1 : 0;
						}
					}
					if (Shared >= 2)
					{
						return;
					}
					for (std::size_t Mine = 0; Mine < (Laid.Count == 4 ? 2u : 1u); ++Mine)
					{
						for (std::size_t Theirs = 0; Theirs < (Base.Count == 4 ? 2u : 1u); ++Theirs)
						{
							if (TrianglesOverlap(Triangles(Laid, Mine), Triangles(Base, Theirs), Sliver))
							{
								Factor = std::min(Factor, Needed * (1.0f - Before));
								return;
							}
						}
					}
				};
				// A polygon over many cells (a floor near the eye) is not listed in them: it is among the large ones, which every
				// polygon looks at, and it looks at every polygon laid before it.
				const bool bLarge = (X1 - X0 + 1) * (Y1 - Y0 + 1) > LargeCells;
				if (bLarge)
				{
					for (const uint32 Under : Done)
					{
						Consider(Under);
					}
				}
				else
				{
					for (const uint32 Under : Large)
					{
						Consider(Under);
					}
					for (int32_t Y = Y0; Y <= Y1; ++Y)
					{
						for (int32_t X = X0; X <= X1; ++X)
						{
							for (const uint32 Under : Cells[static_cast<std::size_t>(Y * Across + X)])
							{
								Consider(Under);
							}
						}
					}
				}
				Scale[Number] = std::max(Factor, 0.9f);
				Laid.Distance *= Scale[Number];
				Planes[Number] = Laid;
				Done.push_back(Number);
				if (bLarge)
				{
					Large.push_back(Number);
					continue;
				}
				for (int32_t Y = Y0; Y <= Y1; ++Y)
				{
					for (int32_t X = X0; X <= X1; ++X)
					{
						Cells[static_cast<std::size_t>(Y * Across + X)].push_back(Number);
					}
				}
			}
		}
	}

	void FMeshBuffers::Clear()
	{
		Pos.clear();
		Normal.clear();
		Color.clear();
		Uv.clear();
		C0.clear();
		C1.clear();
		C2.clear();
		C3.clear();
	}

	struct FSession::FImpl
	{
		FGameLibrary Library;
		const FIso9660* Disc = nullptr;
		/** A translation's disc opened by itself (Open's TranslationImage), which Disc then is. */
		std::unique_ptr<FIso9660> TranslationDisc;
		/** The asset store giving the translation's glyph widths (FMesFontSheet) to the font the session loads; no files of its own. */
		std::shared_ptr<FDiscAssetStore> TranslationAssets;
		/** "en", or the translation's language. */
		std::string Language;
		/**
		 * The disc the game's sound starts from: Disc (a translation's as the identity the bridge recognized it as,
		 * SoundVouched), or USA disc 1 from the games folder for a translation's with XENO_USA_SOUND=1 (as before).
		 */
		const FIso9660* SoundDisc = nullptr;
		std::optional<FDiscIdentity> SoundVouched;

		/** The game's sound started from SoundDisc, as Open and a state's load start it. */
		TResult<std::unique_ptr<FGameSoundSession>> StartSound() const
		{
			return SoundVouched ? FGameSoundSession::Start(*SoundDisc, *SoundVouched) : FGameSoundSession::Start(*SoundDisc);
		}
		/** The translation's map archives given to the core mended (MendedMapArchives), and whether its windows are the Russian program's. */
		int MendedMaps = 0;
		bool bRussianWindows = false;
		std::unique_ptr<FPsxExecutable> Executable;
		/** The menus the programs run inside themselves; before the loop, which they must outlive. */
		std::unique_ptr<FMenuGameMenus> Menus;
		std::unique_ptr<FGameFileIndex> Index;
		std::unique_ptr<FGameSoundSession> Sound;
		std::unique_ptr<FUnheardGameSound> Unheard;
		/** A listener takes the sound's samples (RenderSound): Step no longer lets the unheard sound pass time. */
		bool bHeard = false;
		/** The listener's latency told the sound (Hear), told again to a sound started afresh (LoadState). */
		int HeardLatency = 0;
		/** The vertical blanks real time brings in play, as Weltall's game screen counts them. */
		FTickClock Vblanks{PsxTiming::FrameSeconds};
		/** The cheats' turbo (SetTurbo, 1 none) and random battles off (the game's setting, kept over every power-on). */
		int Turbo = 1;
		bool bEncountersOff = false;
		/**
		 * The game's other disc, taken where the session asked for it (FDiscDrive): its image, boot program and file
		 * index, kept for every session powered on after (a state loaded, a restart); before the session and the loop,
		 * which must not outlive them.
		 */
		struct FAddedDisc
		{
			std::unique_ptr<FIso9660> Disc;
			std::unique_ptr<FPsxExecutable> Executable;
			std::unique_ptr<FGameFileIndex> Index;
			/** As DiscId names the disc played ("rus.disc2", "usa.disc2"), and the image's file. */
			std::string Id;
			std::string File;
		};
		std::array<FAddedDisc, 2> AddedDiscs;
		/** The game's own saves (SetSaveFolder), given to every session powered on; before the session, which must not outlive it. */
		std::unique_ptr<FSaveStore> Saves;
		std::unique_ptr<FGameSession> Session;
		std::unique_ptr<FGameLoop> Loop;
		/**
		 * Session and Loop are another's (Observe): never destroyed here, let go of instead; the menus are that session's
		 * own (FMenuGameMenus, which the story walk's run gives it), the session seen last tells a new game from the same.
		 */
		bool bObserved = false;
		const FMenuGameMenus* ObservedMenus = nullptr;
		const FGameSession* ObservedSession = nullptr;
		/** Kept from Open: Restart powers the console on again with it. */
		std::optional<FDiscIdentity> Identity;
		/**
		 * The disc played, as Weltall names a disc's own files (DiscReleaseId: "usa.disc1"; the Russian translation's
		 * "rus.disc1", as its asset store is named; a patched copy Weltall knows ".patched" after its release's): what the
		 * display keys a movie's replacement by, beside the movie's number (a translation's movie is its own).
		 */
		std::string DiscId;

		/** The disc Open played (0 the first), the games folder, and the translation's image (empty: the USA disc). */
		int PlayedNumber = 0;
		std::string GamesFolder;
		std::string TranslationImage;
		/** The session's drive (IGameDiscDrive): a disc the session was not given is looked for where the player keeps them. */
		class FDiscDrive final : public IGameDiscDrive
		{
		public:
			explicit FDiscDrive(FImpl& InOwner) : Owner(InOwner) {}
			void Seek(int32 Number) override { Owner.SeekDisc(Number); }

		private:
			FImpl& Owner;
		};
		std::unique_ptr<FDiscDrive> Drive;
		/**
		 * A disc the session asked for and did not find (-1 none): the game waits on it (the story's "INSERT DISC 2", a
		 * save of that disc), the display says what to put where, and Step looks again every DiscLookSeconds, so an
		 * image put in meanwhile is taken without the player's confirming first. The folders' entries seen at the last
		 * look (names, sizes, times): unchanged, they are not scanned again.
		 */
		int WantedDisc = -1;
		std::chrono::steady_clock::time_point DiscLookedAt{};
		std::string DiscFoldersSeen;
		static constexpr double DiscLookSeconds = 1.0;

		/** The folders a disc is looked for in: the translation's image's own folder first, then the games folder. */
		std::vector<std::filesystem::path> DiscFolders() const
		{
			std::vector<std::filesystem::path> Folders;
			if (!TranslationImage.empty())
			{
				Folders.push_back(std::filesystem::absolute(std::filesystem::u8path(TranslationImage)).parent_path());
			}
			const std::filesystem::path Games = std::filesystem::absolute(std::filesystem::u8path(GamesFolder));
			std::error_code Error;
			if (Folders.empty() || !std::filesystem::equivalent(Folders[0], Games, Error))
			{
				Folders.push_back(Games);
			}
			return Folders;
		}

		/** A path as UTF-8 (the display's strings are). */
		static std::string Utf8Of(const std::filesystem::path& Path)
		{
			const std::u8string Name = Path.u8string();
			return std::string(Name.begin(), Name.end());
		}

		/** Every entry under the folders by name, size and time: what a scan of them would see. */
		static std::string FolderEntries(const std::vector<std::filesystem::path>& Folders)
		{
			std::string Seen;
			std::error_code Error;
			for (const std::filesystem::path& Folder : Folders)
			{
				for (auto It = std::filesystem::recursive_directory_iterator(Folder, std::filesystem::directory_options::skip_permission_denied, Error);
					 !Error && It != std::filesystem::recursive_directory_iterator(); It.increment(Error))
				{
					std::error_code Quiet;
					Seen += Utf8Of(It->path()) + '|' + std::to_string(It->is_regular_file(Quiet) ? It->file_size(Quiet) : 0) + '|'
						+ std::to_string(It->last_write_time(Quiet).time_since_epoch().count()) + '\n';
				}
			}
			return Seen;
		}

		/** The image File opened as the session reads a disc (as Open opens the translation's): its boot program and index read; an error, or empty. */
		static std::string OpenAddedDisc(const std::filesystem::path& File, FAddedDisc& Out)
		{
			auto Image = FCdImage::Open(File);
			if (!Image)
			{
				return Image.Error().Message;
			}
			auto Disc = FIso9660::Open(std::move(*Image));
			if (!Disc)
			{
				return Disc.Error().Message;
			}
			Out.Disc = std::make_unique<FIso9660>(std::move(*Disc));
			auto Program = ReadBootExecutable(*Out.Disc);
			if (!Program)
			{
				return "its boot program cannot be read";
			}
			auto Read = FGameFileIndex::Read(*Program);
			if (!Read)
			{
				return "its file index cannot be read: " + Read.Error().Message;
			}
			Out.Executable = std::make_unique<FPsxExecutable>(std::move(*Program));
			Out.Index = std::make_unique<FGameFileIndex>(std::move(*Read));
			return {};
		}

		/**
		 * The drive asked for disc Number (IGameDiscDrive::Seek): the one of the kind played, found by content
		 * (SurveyDiscs: the translation's disc of that number, the USA release's), opened, its program and index read
		 * and kept, and given to the session (AddDisc), as Weltall's game screen does (GameLoopScreen.cpp, SeekDisc). The
		 * session reads its files from the first disc, which holds every file; of the second only its movies (FindMovie
		 * over its index, the sectors of its image). Nothing found: wanted, and looked for again from Step.
		 */
		void SeekDisc(int32 Number)
		{
			if (Number < 0 || Number >= static_cast<int32>(AddedDiscs.size()) || Number == PlayedNumber || !Session || bObserved)
			{
				return;
			}
			FAddedDisc& Added = AddedDiscs[static_cast<std::size_t>(Number)];
			if (!Added.Index)
			{
				WantedDisc = Number;
				const std::vector<std::filesystem::path> Folders = DiscFolders();
				std::string Entries = FolderEntries(Folders);
				if (Entries == DiscFoldersSeen)
				{
					return;
				}
				DiscFoldersSeen = std::move(Entries);
				const bool bTranslation = !TranslationImage.empty();
				const Xeno::EDiscKind Kind = bTranslation ? (Number == 0 ? Xeno::EDiscKind::RussianDisc1 : Xeno::EDiscKind::RussianDisc2)
					: (Number == 0 ? Xeno::EDiscKind::UsaDisc1 : Xeno::EDiscKind::UsaDisc2);
				std::filesystem::path File;
				for (const std::filesystem::path& Folder : Folders)
				{
					if (File = Xeno::SurveyDiscs(Folder).First(Kind); !File.empty())
					{
						break;
					}
				}
				if (File.empty())
				{
					return;
				}
				FAddedDisc Opened;
				if (const std::string Why = OpenAddedDisc(File, Opened); !Why.empty())
				{
					std::fprintf(stderr, "xeno: disc %d at %s cannot be used: %s\n", Number + 1, Utf8Of(File).c_str(), Why.c_str());
					return;
				}
				const std::string Release = bTranslation ? std::string("rus") : std::string("usa");
				Opened.Id = Release + ".disc" + std::to_string(Number + 1);
				Opened.File = Utf8Of(File);
				Added = std::move(Opened);
				std::fprintf(stderr, "xeno: disc %d found where the game asked for it: %s\n", Number + 1, Added.File.c_str());
			}
			Session->AddDisc(Number, Added.Disc->Image(), *Added.Index);
			WantedDisc = -1;
			DiscFoldersSeen.clear();
		}

		/** The id of disc Number (0 the first) as DiscId names the disc played; empty for a disc not taken. */
		const std::string& IdOfDisc(int Number) const
		{
			static const std::string None;
			return Number == PlayedNumber ? DiscId : Number >= 0 && Number < static_cast<int>(AddedDiscs.size()) ? AddedDiscs[static_cast<std::size_t>(Number)].Id : None;
		}

		FDrawOptions Options;
		std::string PackFolder;
		/** The pack's pictures by name: 1 a .bc7, 2 a .png (the .png wins, as in the user's core). */
		std::unordered_map<uint64, uint8> Pack;
		std::string PagePackFolder;
		std::unordered_map<uint64, uint8> PagePack;
		/** Scenery regions resolved since the map loaded; the characters' and the 2D layer's every frame. */
		std::unordered_map<uint64, FHdHit> SceneryHits;
		std::unordered_map<uint64, FHdHit> FrameHits;
		int HdUpload = 0, HdRect = 0, HdSplit = 0, FromVram = 0;
		/** Primitives whose picture holds only some of the texels they show (the rest drawn from VRAM); the sprite pieces among them. */
		int HdBeyond = 0, SpriteBeyond = 0, ScreenBeyond = 0;
		/** Semi-transparent primitives drawn from a pack picture with texels that do not blend; a battle's quads that are no sprite's part (glyphs). */
		int KindsPlainDrawn = 0, BattleGlyphs = 0, KindsRimDrawn = 0, KindsRimTexels = 0, KindsRimScenery = 0;
		FReadPicture Reader;
		/** Why regions found no picture (counted once per region resolved): no upload under them, more than one, a name the pack lacks. */
		mutable int MissNoUpload = 0, MissSplit = 0, MissName = 0;
		/** Drawn-rectangle hits by the column tried: a texel before, as given, a texel after. */
		mutable std::array<int, 3> RectHitsByShift{};
		mutable int PageHits = 0;
		mutable std::string MissLog;
		/** Which of the sweep's tallies a primitive that asks for a pack picture goes into (particles go into none). */
		enum class ETally : uint8 { None, Sprite, Screen };
		/** The sweep's tallies (FFrameInfo has what each means): sprites and scenery per BuildWorld, the 2D layer per BuildScreen. */
		int SpritePieces = 0, SpriteHd = 0, SpritePartial = 0, SpriteVram = 0, SpriteNoUpload = 0, SpriteAllInPack = 0, SpriteSplitGaps = 0;
		int ScreenTextured = 0, ScreenHd = 0, ScreenNoUpload = 0, ScreenAllInPack = 0;
		/** Sprite pieces and 2D primitives drawn from VRAM (in whole or in part) because their picture is not loaded yet. */
		int SpriteWaiting = 0, ScreenWaiting = 0;
		int SceneryHd = 0, SceneryVram = 0, SceneryHdMixed = 0;
		/** Field scenery polygons laid on one drawn before them, drawn nearer the eye (FFrameInfo::SceneryLaid). */
		int SceneryLaid = 0;
		/** The last BuildWorld's triangles that blend (not opaque). */
		int WorldBlended = 0;
		/**
		 * On stderr, XENO_TALLY_LOG=1: each piece not wholly from the pack although every upload under it has a picture (the
		 * lookup's own failing); =2: every piece not wholly from the pack.
		 */
		const int TallyLog = std::getenv("XENO_TALLY_LOG") != nullptr ? std::atoi(std::getenv("XENO_TALLY_LOG")) : 0;
		/** XENO_SPRITE_PALETTES: the (upload, palette) pairs under the sprite pieces drawn, with their CLUT, until TakeSpritePalettes. */
		const bool bLogSpritePalettes = std::getenv("XENO_SPRITE_PALETTES") != nullptr;
		struct FSpritePalette
		{
			int ClutX = 0, ClutY = 0, Depth = 0;
			long long Pieces = 0;
			std::string Colours;
		};
		std::map<uint64, FSpritePalette> SpritePalettes;
		/** The pack's palettes by upload (ClassifySpriteQuad's report), built when first asked for. */
		std::unordered_map<uint32, std::vector<uint32>> PackByUpload;

		void NoteSpritePalettes(const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, int MinU, int MinV, int Wide, int High)
		{
			const int Colours = Page.Depth == ETextureDepth::Indexed4 ? 16 : Page.Depth == ETextureDepth::Indexed8 ? 256 : 0;
			for (const FBeetleTexturePart& Part : PartsUnder(Vram, Page, Clut, MinU, MinV, Wide, High))
			{
				FSpritePalette& Entry = SpritePalettes[PackKey(Part.Upload, Part.Palette)];
				if (Entry.Pieces++ == 0)
				{
					Entry.ClutX = Clut.X;
					Entry.ClutY = Clut.Y;
					Entry.Depth = static_cast<int>(Page.Depth);
					for (int Color = 0; Color < Colours; ++Color)
					{
						char Unit[8];
						std::snprintf(Unit, sizeof(Unit), "%04x", Vram.TexelAt(Clut.X + Color, Clut.Y));
						Entry.Colours += Unit;
					}
				}
			}
		}
		/**
		 * On stderr, XENO_DUMP_2D=1: every primitive of a 2D list and every battle quad as it is pushed (corners with their
		 * texels, page, CLUT, blend, drawing area, texel bounds) and the path its texels took (DumpPath: the pack's picture
		 * by upload or by rectangle, cut along uploads, VRAM, waiting for its picture).
		 */
		const bool bDump2D = std::getenv("XENO_DUMP_2D") != nullptr;
		std::string DumpPath;

		/** A drawing not from the pack, noted for a frame report (FrameReport's summary). */
		struct FReportMiss
		{
			/** "sprite", "2D", "other" (particles, effects, world map pieces), "model" (a model's texture: scenery, gears, objects). */
			std::string Kind;
			/** The upload's name as the pack's files are named ("<upload>-<palette>"), a picture's file, or "-" (no upload tracked). */
			std::string Name;
			std::string Why;
			/** The upload's size in VRAM units, its texels per unit, where it lies in VRAM (-1 unknown). */
			int UnitsWide = 0, UnitsHigh = 0, Per = 1, UploadX = -1, UploadY = -1;
			std::string Who;
		};
		/**
		 * F6's frame report being built (FSession::FrameReport): the dumps' lines (XENO_DUMP_2D's, XENO_DUMP_OBJECTS',
		 * XENO_TALLY_LOG=2's, and the field's polygons and sprite pieces) go into Lines instead of stderr, and every drawing
		 * not from the pack is noted. Who: what is being drawn, for the notes (a sprite's actor and frame, a model).
		 */
		struct FFrameReport
		{
			std::string Lines;
			std::vector<FReportMiss> Misses;
			std::string Who;
		};
		FFrameReport* Report = nullptr;

		/**
		 * F6's state to go back to (SetRollingState): the newest quiet moment's (CaptureSaveState: where F5 would save), taken
		 * once RollingEvery frames have run since the last one (then tried every frame until the game is quiet: the try costs
		 * nothing where it is not), or the state F5 saved or a load began from; and every frame since it: its buttons,
		 * vertical blanks, whether the turbo ran it, the cheats used since (which a replay cannot repeat).
		 */
		int RollingEvery = 0;
		std::optional<FSaveState> Rolling;
		std::string RollingFrom;
		std::chrono::steady_clock::time_point RollingAt;
		std::vector<uint16> InputsSince;
		long long VblanksSince = 0;
		int TurboStepsSince = 0, CheatsSince = 0;
		/** The captures' costs (for choosing RollingEvery): tries, captures, their total and longest time; the longest failed try. */
		long long RollingTries = 0, RollingCaptures = 0;
		double RollingUsecTotal = 0.0, RollingUsecLongest = 0.0, RollingTryUsecLongest = 0.0;

		/** The game from State on (captured, saved, loaded): no frames since it yet. */
		void RollFrom(std::optional<FSaveState> State, const char* From)
		{
			Rolling = std::move(State);
			RollingFrom = Rolling ? From : "";
			RollingAt = std::chrono::steady_clock::now();
			InputsSince.clear();
			VblanksSince = 0;
			TurboStepsSince = 0;
			CheatsSince = 0;
		}

		/** A dump's text: into the frame report being built, else onto stderr (the XENO_DUMP_* variables). */
		void Dump(const char* Format, ...) const
		{
			char Text[1024];
			va_list Arguments;
			va_start(Arguments, Format);
			const int Length = std::vsnprintf(Text, sizeof(Text), Format, Arguments);
			va_end(Arguments);
			if (Length < 0)
			{
				return;
			}
			if (Report != nullptr)
			{
				Report->Lines.append(Text, static_cast<std::size_t>(std::min<int>(Length, static_cast<int>(sizeof(Text)) - 1)));
			}
			else
			{
				std::fputs(Text, stderr);
			}
		}
		/** The 2D primitives' and quads' dump: XENO_DUMP_2D, or a frame report. */
		bool Dumping2D() const { return bDump2D || Report != nullptr; }
		/** XENO_TALLY_LOG's level; a frame report takes every piece not wholly from the pack (2). */
		int TallyLevel() const { return Report != nullptr ? 2 : TallyLog; }

		/** For a frame report: an upload under a drawing not from the pack (its first unit in VRAM worked out as LogMiss does). */
		void NoteReportPart(const char* Kind, const FTexturePage& Page, int U0, int V0, const FBeetleTexturePart& Part, const std::string& Why)
		{
			const int Per = TexelsPerUnit(Page.Depth);
			const int FromTexel = U0 + Part.U - Part.FromU;
			FReportMiss Miss;
			Miss.Kind = Kind;
			Miss.Name = BeetleTextureFileName({Part.Upload, Part.Palette});
			Miss.Why = Why;
			Miss.UnitsWide = Part.UploadUnitsWide;
			Miss.UnitsHigh = Part.UploadUnitsHigh;
			Miss.Per = Per;
			Miss.UploadX = Page.X + (FromTexel >= 0 ? FromTexel / Per : -((-FromTexel + Per - 1) / Per));
			Miss.UploadY = Page.Y + V0 + Part.V - Part.FromV;
			Miss.Who = Report->Who;
			Report->Misses.push_back(std::move(Miss));
		}
		/** The pack's palettes of an upload besides the one asked for (built when first asked for, as NoteSpriteMiss does). */
		int OtherPalettes(const FBeetleTexturePart& Part)
		{
			if (PackByUpload.empty())
			{
				for (const auto& [Key, Kind] : Pack)
				{
					PackByUpload[static_cast<uint32>(Key >> 32)].push_back(static_cast<uint32>(Key));
				}
			}
			const auto Found = PackByUpload.find(Part.Upload);
			return Found == PackByUpload.end() ? 0 : static_cast<int>(Found->second.size());
		}
		/**
		 * For a frame report: whose a field character's quad is: its actor and pass, the sprite file the actor's sprite was
		 * made from (a party slot's: the character's set, as the user's layouts name it, <427 + character>_0; or the map's),
		 * and the frame it shows (the core counts from 1, the layouts from 0).
		 */
		static std::string SpriteWho(const FFieldProgram& Field, const FFieldCharacterView& Character)
		{
			const int Actor = static_cast<int>(Character.BlendKey >> 3);
			std::string Who = "actor " + std::to_string(Actor) + " pass " + std::to_string(Character.BlendKey & 7);
			const FFieldSprites& Sprites = Field.Runtime().Sprites();
			const FSprite* Sprite = Sprites.SpriteOf(Actor);
			if (Sprite == nullptr)
			{
				return Who;
			}
			std::string File = "sprite file not known";
			const FEventContext& Context = Field.Runtime().Context();
			for (int Slot = 0; Context.PartySprites != nullptr && Slot < FPartySpriteFiles::Slots; ++Slot)
			{
				if (Sprite->PrimaryFile == &Context.PartySprites->Buffer(Slot))
				{
					const int Number = Context.PartySprites->File(Slot);
					File = "party slot " + std::to_string(Slot) + " file " + std::to_string(Number)
						+ (Number < FPartySpriteFiles::FirstGearFile ? " (set " + std::to_string(427 + Number) + "_0)" : " (a gear's)");
				}
			}
			for (int Slot = 0; Sprites.MapFile(Slot) != nullptr; ++Slot)
			{
				if (Sprite->PrimaryFile == Sprites.MapFile(Slot))
				{
					File = "map sprite file " + std::to_string(Slot);
				}
			}
			if (Sprite->CurrentFile != nullptr && Sprite->CurrentFile != Sprite->PrimaryFile)
			{
				File += ", playing another file's animation";
			}
			return Who + ", " + File + ", frame " + std::to_string(Sprite->Frame) + " (layout frame " + std::to_string(static_cast<int>(Sprite->Frame) - 1) + ")";
		}

		/** XENO_WITHOUT_T8=1: draws as before the fixes of 13.11 (caption rows, window frames, pictures short of a piece), for comparisons. */
		static bool WithoutTask8()
		{
			static const bool bWithout = std::getenv("XENO_WITHOUT_T8") != nullptr;
			return bWithout;
		}

		/** XENO_WITHOUT_T9=1: a pack picture's rim over a transparent texel drawn plain, as before 13.11 afternoon (for comparisons). */
		static bool WithoutTask9()
		{
			static const bool bWithout = std::getenv("XENO_WITHOUT_T9") != nullptr;
			return bWithout;
		}

		/**
		 * Which texels of a pack picture blend (TexelKinds): the GPU blends a semi-transparent primitive's texel only where
		 * its colour has bit 15 set, and the pack's pictures do not carry that (a BC7's alpha is not the texel's kind as
		 * Beetle's dumps mark it: the battle's command ring's picture has alpha 255 on 82 % of its visible points over
		 * blending texels, a menu window frame's picture alpha 0 on the points it draws over plain ones), so each picture
		 * texel takes the kind of the original texel under it, as Weltall's renderer gives a picture without kinds
		 * (TextureModLibrary.h, bKindsFromAlpha). A transparent texel (colour 0) has no kind: the GPU never draws it. A
		 * picture's rim drawn past the original's edge over it shows the drawn texel beside it and takes that one's kind
		 * (the display looks for the nearest, main.gd PICTURE_KINDS): 0 marks it.
		 * Kept by the picture's key: a pack picture's name is its texels' and CLUT's, so its kinds never change; a "page:"
		 * key is the scene's (forgotten with it).
		 */
		struct FTexelKinds
		{
			int U = 0, V = 0, Width = 0, Height = 0;
			std::vector<uint8> Blends;
			bool bMixed = false, bPlain = false;
		};
		std::unordered_map<std::string, FTexelKinds> KindsOf;
		static constexpr uint8 KindTransparent = 0, KindPlain = 128, KindBlends = 255;

		/** Notes the kinds of the picture Key, which holds Width x Height texels of the page from (U, V) on (page texels). */
		void NoteKinds(const std::string& Key, const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, int U, int V, int Width, int Height)
		{
			if (WithoutTask8() || Key.empty() || Width <= 0 || Height <= 0 || Width > 1024 || Height > 1024 || KindsOf.contains(Key))
			{
				return;
			}
			FTexelKinds& Kinds = KindsOf[Key];
			Kinds.U = U;
			Kinds.V = V;
			Kinds.Width = Width;
			Kinds.Height = Height;
			Kinds.Blends.resize(static_cast<std::size_t>(Width * Height));
			bool bBlends = false, bPlain = false;
			for (int Row = 0; Row < Height; ++Row)
			{
				for (int Column = 0; Column < Width; ++Column)
				{
					const uint16 Color = TexelColor(Vram, Page, Clut, U + Column, V + Row);
					const bool bBlending = Color != 0 && (Color & 0x8000) != 0;
					bBlends = bBlends || bBlending;
					bPlain = bPlain || (Color != 0 && !bBlending);
					Kinds.Blends[static_cast<std::size_t>(Row * Width + Column)] =
						bBlending ? KindBlends : Color != 0 || WithoutTask9() ? KindPlain : KindTransparent;
				}
			}
			Kinds.bMixed = bBlends && bPlain;
			Kinds.bPlain = bPlain;
		}

		/**
		 * Counts a semi-transparent primitive drawn from the picture Key whose own texels U0..U1, V0..V1 (page texels,
		 * inclusive) hold a transparent texel with a blending one within two texels among them: the picture's rim there
		 * blends now (main.gd PICTURE_KINDS looks that far), where it was drawn plain.
		 */
		void NoteRim(const std::string& Key, int U0, int V0, int U1, int V1)
		{
			const auto Found = KindsOf.find(Key);
			if (Found == KindsOf.end() || WithoutTask9())
			{
				return;
			}
			const FTexelKinds& Kinds = Found->second;
			const auto KindAt = [&Kinds](int U, int V)
			{
				const int Column = U - Kinds.U, Row = V - Kinds.V;
				return Column < 0 || Row < 0 || Column >= Kinds.Width || Row >= Kinds.Height ? KindTransparent
																							 : Kinds.Blends[static_cast<std::size_t>(Row * Kinds.Width + Column)];
			};
			int Rim = 0;
			for (int V = V0; V <= V1; ++V)
			{
				for (int U = U0; U <= U1; ++U)
				{
					if (KindAt(U, V) != KindTransparent)
					{
						continue;
					}
					bool bNearBlending = false;
					for (int Y = std::max(V0, V - 2); Y <= std::min(V1, V + 2) && !bNearBlending; ++Y)
					{
						for (int X = std::max(U0, U - 2); X <= std::min(U1, U + 2) && !bNearBlending; ++X)
						{
							bNearBlending = KindAt(X, Y) == KindBlends;
						}
					}
					Rim += bNearBlending ? 1 : 0;
				}
			}
			KindsRimDrawn += Rim > 0 ? 1 : 0;
			KindsRimTexels += Rim;
			// A scene's model on a page with pictures laid in (only where a picture of the pack covers the texel can a rim be there).
			KindsRimScenery += Rim > 0 && Key.rfind("page:", 0) == 0 ? 1 : 0;
		}

		/**
		 * NoteKinds, and counts a semi-transparent primitive drawn from the picture whose texels are not all blending (drawn
		 * otherwise than before the kinds were taken from VRAM: all its texels blended then).
		 */
		void NoteSemiPicture(const std::string& Key, const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, int U, int V, int Width, int Height)
		{
			NoteKinds(Key, Vram, Page, Clut, U, V, Width, Height);
			const auto Found = KindsOf.find(Key);
			KindsPlainDrawn += Found != KindsOf.end() && Found->second.bPlain ? 1 : 0;
		}

		void DumpCorners(const std::array<FCorner, 4>& Corners, int Count) const
		{
			for (int Corner = 0; Corner < Count; ++Corner)
			{
				const FCorner& At = Corners[static_cast<std::size_t>(Corner)];
				Dump(" (%g,%g uv %g,%g)", At.Pos[0], At.Pos[1], At.U, At.V);
			}
		}

		/**
		 * One line for a piece not wholly from the pack: why (no upload, uploads lacking, all in pack), its page, CLUT and
		 * texels, its corners' places (screen pixels for the 2D layer, Godot's view space for sprites) and each upload under
		 * it: its name, where the upload lies in VRAM (units) and its size.
		 */
		void LogMiss(ETally Tally, const char* How, const FTexturePage& Page, const FClutPosition& Clut, int U0, int V0, int Wide, int High,
			const std::array<FCorner, 4>& Corners, int Count, const std::vector<FBeetleTexturePart>& Parts, int Lacking, const FVram* Vram = nullptr)
		{
			const bool bAllIn = !Parts.empty() && Lacking == 0;
			if (TallyLevel() < 1 || (TallyLevel() < 2 && !bAllIn))
			{
				return;
			}
			const char* Kind = Tally == ETally::Sprite ? "sprite" : Tally == ETally::Screen ? "2D" : "other";
			Dump("miss %s %s %s page %d,%d depth %d clut %d,%d region u %d v %d %dx%d at", Kind, How,
				Parts.empty() ? "no-upload" : bAllIn ? "all-in-pack" : "lacking", Page.X, Page.Y, static_cast<int>(Page.Depth), Clut.X, Clut.Y, U0, V0, Wide,
				High);
			for (int Corner = 0; Corner < Count; ++Corner)
			{
				const FCorner& At = Corners[static_cast<std::size_t>(Corner)];
				Dump(" (%g,%g uv %g,%g)", At.Pos[0], At.Pos[1], At.U, At.V);
			}
			const int Per = TexelsPerUnit(Page.Depth);
			for (const FBeetleTexturePart& Part : Parts)
			{
				// The upload's first unit: the part's first texel in VRAM, less where the part begins in its upload.
				const int FromTexel = U0 + Part.U - Part.FromU;
				const int UploadX = Page.X + (FromTexel >= 0 ? FromTexel / Per : -((-FromTexel + Per - 1) / Per)), UploadY = Page.Y + V0 + Part.V - Part.FromV;
				Dump(" [%s%s upload at %d,%d %dx%d units, part u %d v %d %dx%d]", BeetleTextureFileName({Part.Upload, Part.Palette}).c_str(),
					HasPicture(Part) ? " in-pack" : "", UploadX, UploadY, Part.UploadUnitsWide, Part.UploadUnitsHigh, Part.U, Part.V, Part.Width, Part.Height);
			}
			Dump("\n");
			if (Report == nullptr)
			{
				return;
			}
			// The report's notes: each upload under the piece without its picture (by its name, or found by content), why.
			if (Parts.empty())
			{
				FReportMiss Miss;
				Miss.Kind = Kind;
				Miss.Name = "-";
				Miss.Why = std::string(How) + ": no upload tracked under it (the port's own rows, or written by the CPU)";
				Miss.Who = Report->Who;
				Report->Misses.push_back(std::move(Miss));
				return;
			}
			const uint32 View = PackTextureView(Page, Clut);
			for (const FBeetleTexturePart& Part : Parts)
			{
				const bool bByName = HasPicture(Part);
				const bool bByContent = !bByName && Vram != nullptr && HasPictureThrough(*Vram, View, Part, true);
				if (bAllIn || (!bByName && !bByContent))
				{
					std::string Why = std::string(How) + (bAllIn ? ": every upload under it is in the pack (the lookup's own failing)"
						: ": not in the pack, none found by content");
					if (!bAllIn)
					{
						if (const int Others = OtherPalettes(Part); Others > 0)
						{
							Why += " (the pack has this upload under " + std::to_string(Others) + " other palette" + (Others > 1 ? "s" : "") + ")";
						}
					}
					NoteReportPart(Kind, Page, U0, V0, Part, Why);
				}
			}
		}
		/** Upload names the pack lacks under pieces not wholly from it, until TakeMissingNames. */
		std::set<std::string> MissingNames;
		/** Whether a scenery region on a page with pictures has texels outside the pack's pictures, since the map loaded. */
		std::unordered_map<uint64, bool> SceneryMixed;

		/** Forgets what was worked out for the map in VRAM (a new map, pack, options or game). */
		void ForgetScenery()
		{
			SceneryHits.clear();
			SceneryMixed.clear();
			PageStates.clear();
			UsedIndices.clear();
		}

		bool HasPicture(const FBeetleTexturePart& Part) const
		{
			return InPack(PackKey(Part.Upload, Part.Palette)) != nullptr || InPack(PackKey(Part.Upload, Part.ReducedPalette)) != nullptr;
		}

		/** HasPicture, a picture found through a palette agreeing on the part's colours counted too (PictureName). */
		bool HasPictureThrough(const FVram& Vram, uint32 View, const FBeetleTexturePart& Part, bool bByContent = false) const
		{
			return PictureName(Vram, View, Part, bByContent) != 0;
		}

		/**
		 * A piece not wholly drawn from the pack, tallied: the names of the uploads under it the pack has no picture of
		 * (by the full CLUT, as the pack names most pictures), no upload under it at all, or every upload under it in the
		 * pack (the lookup's own failing: the region reaches past them or is not cut). Returns the uploads lacking.
		 */
		int TallyMiss(ETally Tally, const std::vector<FBeetleTexturePart>& Parts)
		{
			int Lacking = 0;
			for (const FBeetleTexturePart& Part : Parts)
			{
				if (!HasPicture(Part))
				{
					++Lacking;
					MissingNames.insert(BeetleTextureFileName({Part.Upload, Part.Palette}));
				}
			}
			if (Parts.empty())
			{
				++(Tally == ETally::Sprite ? SpriteNoUpload : ScreenNoUpload);
			}
			else if (Lacking == 0)
			{
				++(Tally == ETally::Sprite ? SpriteAllInPack : ScreenAllInPack);
			}
			if (Tally == ETally::Sprite && bLogSpritePalettes)
			{
				NoteSpriteMiss(Parts, Lacking);
			}
			return Lacking;
		}

		/**
		 * With XENO_SPRITE_PALETTES: a sprite piece not wholly from the pack, by class and the names under it (TakeSpriteMisses):
		 * "a" an upload under it the pack has under no palette, "b" one it has only under other palettes, "c" every upload
		 * under it has its picture (the lookup's own failing), "d" no upload tracked under it, "beyond" a picture holding
		 * fewer texels than the piece shows.
		 */
		std::map<std::pair<std::string, std::string>, long long> SpriteMisses;

		void NoteSpriteMiss(const std::vector<FBeetleTexturePart>& Parts, int Lacking)
		{
			if (PackByUpload.empty())
			{
				for (const auto& [Key, Kind] : Pack)
				{
					PackByUpload[static_cast<uint32>(Key >> 32)].push_back(static_cast<uint32>(Key));
				}
			}
			if (Parts.empty())
			{
				++SpriteMisses[{"d", "-"}];
				return;
			}
			for (const FBeetleTexturePart& Part : Parts)
			{
				const bool bHas = HasPicture(Part);
				if (Lacking > 0 && bHas)
				{
					continue;
				}
				const auto Found = PackByUpload.find(Part.Upload);
				++SpriteMisses[{Lacking == 0 ? "c" : Found != PackByUpload.end() ? "b" : "a", BeetleTextureFileName({Part.Upload, Part.Palette})}];
			}
		}

		/** The parts of uploads under a primitive's texels, as Resolve looks them up (none when they lie outside the page). */
		static std::vector<FBeetleTexturePart> PartsUnder(const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, int MinU, int MinV,
			int Wide, int High)
		{
			if (MinU < 0 || MinV < 0 || MinU >= 256 || MinV >= 256)
			{
				return {};
			}
			FTextureRegion Region;
			Region.View = PackTextureView(Page, Clut);
			Region.U = static_cast<uint8>(MinU);
			Region.V = static_cast<uint8>(MinV);
			Region.Width = static_cast<uint16>(std::clamp(Wide, 1, 256 - MinU));
			Region.Height = static_cast<uint16>(std::clamp(High, 1, 256 - MinV));
			return BeetleTextureParts(Vram, Region);
		}

		/** Whether a scenery polygon's texels (MinU..MaxU, MinV..MaxV, last ones included) lie wholly in uploads the pack has pictures of. */
		bool SceneryRegionMixed(const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, float MinU, float MinV, float MaxU, float MaxV)
		{
			const int U0 = std::clamp(static_cast<int>(std::floor(MinU)), 0, 255), V0 = std::clamp(static_cast<int>(std::floor(MinV)), 0, 255);
			const int Wide = std::clamp(static_cast<int>(std::ceil(MaxU)) - U0 + 1, 1, 256 - U0);
			const int High = std::clamp(static_cast<int>(std::ceil(MaxV)) - V0 + 1, 1, 256 - V0);
			const uint64 Key = static_cast<uint64>(PackTextureView(Page, Clut)) | static_cast<uint64>(U0) << 32 | static_cast<uint64>(V0) << 40
				| static_cast<uint64>(Wide - 1) << 48 | static_cast<uint64>(High - 1) << 56;
			// The pictures laid in may change with the page's state (an animated palette's): the answer is the state's.
			const uint64 StateKey = Key ^ static_cast<uint64>(PageState(Vram, PackTextureView(Page, Clut))) * 0x9E3779B97F4A7C15ull;
			const auto Found = SceneryMixed.find(StateKey);
			if (Found != SceneryMixed.end())
			{
				return Found->second;
			}
			const std::vector<FBeetleTexturePart> Parts = PartsUnder(Vram, Page, Clut, U0, V0, Wide, High);
			bool bMixed = Parts.empty();
			int Covered = 0;
			for (const FBeetleTexturePart& Part : Parts)
			{
				bMixed = bMixed || !HasPictureThrough(Vram, PackTextureView(Page, Clut), Part);
				Covered += Part.Width * Part.Height;
			}
			// Texels outside every tracked upload show the page's own (Covered over-counts only where uploads overlap).
			bMixed = bMixed || Covered < Wide * High;
			return SceneryMixed.emplace(StateKey, bMixed).first->second;
		}

		/** Powers the console on with the opened disc and sound, and sets the player's settings the bridge plays with. */
		std::string PowerOn()
		{
			auto Started = FGameSession::PowerOn(Disc->Image(), *Index, *Executable, *Identity, *Sound);
			if (!Started)
			{
				return Started.Error().Message;
			}
			Session = std::move(*Started);
			// The other disc taken before (a state of it loaded, a restart), and the drive that looks for it when it is not.
			for (std::size_t Number = 0; Number < AddedDiscs.size(); ++Number)
			{
				if (AddedDiscs[Number].Index)
				{
					Session->AddDisc(static_cast<int32>(Number), AddedDiscs[Number].Disc->Image(), *AddedDiscs[Number].Index);
				}
			}
			if (!Drive)
			{
				Drive = std::make_unique<FDiscDrive>(*this);
			}
			Session->SetDiscDrive(Drive.get());
			WantedDisc = -1;
			// The game's own controls and camera, as the core's tests play; gears as their sprites for now.
			FPlayerSettings Settings = Session->Settings();
			Settings.Controls.bAlwaysRun = false;
			Settings.Controls.bWalkIntoDoors = false;
			Settings.Controls.DoorPause = NoDoorPause;
			Settings.Camera.bSteadyFollow = false;
			Settings.Field.GearModels = EFieldGearModels::Off;
			// XENO_ORIGINAL_CULLING=1 (for comparisons): the original's culling of the field's and the battle's polygons (made for
			// its 320-pixel screen) instead of Weltall's InRange (everything a wider view can show).
			if (std::getenv("XENO_ORIGINAL_CULLING") != nullptr)
			{
				Settings.Field.Culling = EFieldCulling::Original;
			}
			// Sprites' mirrored pieces where the original draws them (up to three texels right of where Weltall's fix puts them):
			// the texture pack was drawn over the original's frames. XENO_ALIGNED=1 keeps Weltall's fix (for comparisons).
			Settings.Fixes.Field.bSpriteFramesAligned = std::getenv("XENO_ALIGNED") != nullptr;
			// The Russian translation's field program: its windows' lines and typing (FEventOptions::bRussianWindows).
			// XENO_USA_WINDOWS=1 keeps the USA program's windows with the Russian text (for comparisons).
			Settings.Fixes.Field.bRussianWindows = bRussianWindows && std::getenv("XENO_USA_WINDOWS") == nullptr;
			// The cheat "random battles off" is Weltall's own balance setting (FGameBalance::Encounters, its menu's "Encounters: None").
			if (bEncountersOff)
			{
				Settings.Balance.Encounters = EEncounterRate::None;
			}
			Session->SetSettings(Settings);
			// The Menu the field (and the title) runs inside itself, as Weltall's game screen gives it (GameLoopScreen.cpp,
			// Start): without it a menu stops the game. No settings kept, no keys: the original's menus.
			Session->SetMenus(Menus.get());
			// The game's own saves, as Weltall's game screen gives them (GameLoopScreen.cpp, Start: SetSaves).
			Session->SetSaves(Saves.get());
			ResetScreens();
			return {};
		}

		/**
		 * Everything worked out from the game that ran before (a state loaded over it): the scenery's caches and pages, the
		 * movie followed, the display's pictures of the screen and the VRAM patched with them. The next frame of the new
		 * game is a new scene (SceneKey), so its pages are built again.
		 */
		void ForgetGame()
		{
			ForgetScenery();
			FrameHits.clear();
			SceneKey = -1;
			ResetScreens();
			ScreenPictures.clear();
			PatchedVram.clear();
			PatchedStamp = 0;
			// Another game: F6's state to go back to was the old one's.
			RollFrom(std::nullopt, "");
		}

		const FFieldProgram* Field() const { return Loop ? Loop->Field() : nullptr; }
		const FFieldFrame* Frame() const { return Field() != nullptr ? Field()->LatestFrame() : nullptr; }

		std::string PathOf(uint64 Key, uint8 Kind) const
		{
			char Name[32];
			std::snprintf(Name, sizeof(Name), "%x-%x", static_cast<uint32>(Key >> 32), static_cast<uint32>(Key));
			return PackFolder + "/" + Name + (Kind == 2 ? ".png" : ".bc7");
		}

		const uint8* InPack(uint64 Key) const
		{
			const auto Found = Pack.find(Key);
			return Found != Pack.end() ? &Found->second : nullptr;
		}

		/**
		 * The pack's picture for the texels a primitive shows (MinU, MinV, Wide x High of its page through its CLUT):
		 * as Beetle names them, the upload under them and the CLUT; for a sprite's piece of a 4-bit page, failing that, as
		 * the user's core names a piece drawn from a page loaded in strips, the drawn rectangle's units (one word more to
		 * the right, one row less) and the CLUT.
		 */
		static FTextureRegion WholePage(uint32 View)
		{
			FTextureRegion Region;
			Region.View = View;
			Region.Width = 256;
			Region.Height = 256;
			return Region;
		}

		FHdHit Resolve(const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, int MinU, int MinV, int Wide, int High, bool bSprite) const
		{
			FHdHit Hit;
			Wide = std::clamp(Wide, 1, 256 - MinU);
			High = std::clamp(High, 1, 256 - MinV);
			FTextureRegion Region;
			Region.View = PackTextureView(Page, Clut);
			Region.U = static_cast<uint8>(MinU);
			Region.V = static_cast<uint8>(MinV);
			Region.Width = static_cast<uint16>(Wide);
			Region.Height = static_cast<uint16>(High);
			const int Per = TexelsPerUnit(Page.Depth);
			const std::vector<FBeetleTexturePart> Parts = BeetleTextureParts(Vram, Region);
			bool bCovered = false;
			for (const FBeetleTexturePart& Part : Parts)
			{
				if (Part.U != 0 || Part.V != 0 || Part.Width < Wide || Part.Height < High)
				{
					continue; // the primitive's texels reach past this upload
				}
				bCovered = true;
				if (const uint64 Name = PictureName(Vram, Region.View, Part, true))
				{
					if (const uint8* Kind = InPack(Name))
					{
						Hit.Kind = FHdHit::Upload;
						Hit.Texture = PathOf(Name, *Kind);
						if (const auto Alias = AliasFound.find(PackKey(Part.Upload, Part.Palette)); Alias != AliasFound.end() && Alias->second.Key == Name)
						{
							Hit.Added = Alias->second.Added;
						}
						Hit.AddU = static_cast<float>(Part.FromU - MinU);
						Hit.AddV = static_cast<float>(Part.FromV - MinV);
						Hit.Wide = static_cast<float>(Part.UploadUnitsWide * Per);
						Hit.High = static_cast<float>(Part.UploadUnitsHigh);
						return Hit;
					}
				}
			}
			++(Parts.empty() ? MissNoUpload : bCovered ? MissName : MissSplit);
			if (bSprite && Page.Y >= FVram::Height)
			{
				// The port's own rows (Weltall's stand-ins: a party member's sprite drawn small for a pilot in a gear) have no
				// uploads Beetle would name: their texels are the member's own frame cells, found by content.
				return RegionAlias(Vram, Page, Clut, MinU, MinV, Wide, High);
			}
			if (!bSprite || Page.Depth != ETextureDepth::Indexed4 || Page.Y >= FVram::Height)
			{
				return Hit;
			}
			if (FHdHit Found = RectHit(Vram, Page, Clut, MinU, MinV, Wide, High); Found.Kind != FHdHit::None)
			{
				++RectHitsByShift[1];
				return Found;
			}
			if (FHdHit Found = RegionAlias(Vram, Page, Clut, MinU, MinV, Wide, High); Found.Kind != FHdHit::None)
			{
				return Found;
			}
			FHdHit Found = PageHit(Vram, Page, Clut);
			if (Found.Kind == FHdHit::None && MissLog.size() < 20000)
			{
				// What lies under a sprite piece left without a picture, for the smoke test.
				char Line[256];
				std::snprintf(Line, sizeof(Line), "miss page %d,%d depth %d clut %d,%d region u %d v %d %dx%d:", Page.X, Page.Y,
					static_cast<int>(Page.Depth), Clut.X, Clut.Y, MinU, MinV, Wide, High);
				MissLog += Line;
				for (const FBeetleTexturePart& Part : Parts)
				{
					std::snprintf(Line, sizeof(Line), " [part u %d v %d %dx%d from %d,%d of %dx%d units, %x-%x%s]", Part.U, Part.V, Part.Width, Part.Height,
						Part.FromU, Part.FromV, Part.UploadUnitsWide, Part.UploadUnitsHigh, Part.Upload, Part.Palette,
						InPack(PackKey(Part.Upload, Part.Palette)) ? " IN PACK" : "");
					MissLog += Line;
				}
				MissLog += "\n";
			}
			return Found;
		}

		/** The whole page's picture (the page's 256 rows of 64 units and the CLUT's 16 colours), as the user's core names it. */
		FHdHit PageHit(const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut) const
		{
			FHdHit Hit;
			if (PagePack.empty())
			{
				return Hit;
			}
			std::vector<uint16> Units;
			Units.reserve(64 * 256);
			for (int Y = 0; Y < 256; ++Y)
			{
				for (int X = 0; X < 64; ++X)
				{
					Units.push_back(Vram.At(Page.X + X, Page.Y + Y));
				}
			}
			std::array<uint16, 16> Colors{};
			for (int Color = 0; Color < 16; ++Color)
			{
				Colors[static_cast<std::size_t>(Color)] = Vram.At(Clut.X + Color, Clut.Y);
			}
			const uint64 Key = PackKey(Crc32OfUnits(Units), Crc32OfUnits(Colors));
			const auto Found = PagePack.find(Key);
			if (Found != PagePack.end())
			{
				char Name[32];
				std::snprintf(Name, sizeof(Name), "%x-%x", static_cast<uint32>(Key >> 32), static_cast<uint32>(Key));
				Hit.Kind = FHdHit::Rect;
				Hit.Texture = PagePackFolder + "/" + Name + (Found->second == 2 ? ".png" : ".bc7");
				Hit.Wide = 256.0f;
				Hit.High = 256.0f;
				++PageHits;
			}
			return Hit;
		}

		/** The drawn rectangle's picture for a piece whose first texel column is GameU (npc_rects.py's formula). */
		FHdHit RectHit(const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, int GameU, int MinV, int Wide, int High) const
		{
			FHdHit Hit;
			const int X0 = GameU >> 2;
			const int Words = ((GameU + Wide + 1) >> 2) - X0;
			const int Rows = High - 1;
			const uint64 Key = RectKey(Vram, Page, Clut, GameU, MinV, Wide, High);
			if (Key == 0)
			{
				return Hit;
			}
			if (const uint8* Kind = InPack(Key))
			{
				Hit.Kind = FHdHit::Rect;
				Hit.Texture = PathOf(Key, *Kind);
				Hit.AddU = static_cast<float>(-X0 * 4);
				Hit.AddV = static_cast<float>(-MinV);
				Hit.Wide = static_cast<float>(Words * 4);
				Hit.High = static_cast<float>(Rows);
			}
			return Hit;
		}

		/** The drawn rectangle's name (RectHit) as the pack's key, 0 where the piece has none. */
		uint64 RectKey(const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, int GameU, int MinV, int Wide, int High) const
		{
			if (GameU < 0)
			{
				return 0;
			}
			const int X0 = GameU >> 2;
			const int Words = ((GameU + Wide + 1) >> 2) - X0;
			const int Rows = High - 1;
			if (Words <= 0 || Rows <= 0)
			{
				return 0;
			}
			std::vector<uint16> Units;
			Units.reserve(static_cast<std::size_t>(Words * Rows));
			for (int Y = 0; Y < Rows; ++Y)
			{
				for (int X = 0; X < Words; ++X)
				{
					Units.push_back(Vram.At(Page.X + X0 + X, Page.Y + MinV + Y));
				}
			}
			std::array<uint16, 16> Colors{};
			for (int Color = 0; Color < 16; ++Color)
			{
				Colors[static_cast<std::size_t>(Color)] = Vram.At(Clut.X + Color, Clut.Y);
			}
			return PackKey(Crc32OfUnits(Units), Crc32OfUnits(Colors));
		}

		/**
		 * Which pictures a texture page through a CLUT has laid in now (PageImage): a hash of each upload part's place and
		 * the picture found for it, 0 for none. A program that animates a palette or texels changes the names of the uploads
		 * under them (Beetle names an upload by its units and the palette as it is), so this is the page's picture's state,
		 * worked out once a frame (PageStates is cleared with each BuildWorld).
		 */
		uint32 PageState(const FVram& Vram, uint32 View)
		{
			const auto Found = PageStates.find(View);
			if (Found != PageStates.end())
			{
				return Found->second;
			}
			uint32 State = 0;
			for (const FBeetleTexturePart& Part : BeetleTextureParts(Vram, WholePage(View)))
			{
				if (const uint64 Name = PictureName(Vram, View, Part))
				{
					State = (State ^ static_cast<uint32>(Name ^ Name >> 32)) * 16777619u;
					State = (State ^ static_cast<uint32>(Part.U | Part.V << 8 | Part.Width << 16 | (Part.Height & 0xFF) << 24)) * 16777619u;
					State |= 1;
				}
			}
			return PageStates.emplace(View, State).first->second;
		}
		std::unordered_map<uint32, uint32> PageStates;

		/**
		 * Pictures of the pack found through palettes that agree on every colour an upload's texels use: its texels show the
		 * same through each, so a picture made under one is the picture under all (a palette animated in colours an upload
		 * does not use, as the world map's water shimmer in the tail of its fog palettes: the land under every state of
		 * it). Keyed by the upload, the view's depth and those colours (UsedColoursKey); filled as pictures are found by
		 * their own names, so a state is known once a state agreeing with it has been seen with its picture.
		 */
		mutable std::unordered_map<uint64, uint64> SamePalettePictures;
		/** The CLUT indices the texels of an upload's parts under a page use, by upload and texture view (for the scene in VRAM). */
		mutable std::unordered_map<uint64, std::array<uint64, 4>> UsedIndices;

		uint64 UsedColoursKey(const FVram& Vram, uint32 View, const FBeetleTexturePart& Part) const
		{
			const FTexturePage Page = TextureViewPage(View);
			if (Page.Depth == ETextureDepth::Direct15 || Page.Y >= FVram::Height)
			{
				return 0;
			}
			const FClutPosition Clut = TextureViewClut(View);
			const uint64 UsedKey = static_cast<uint64>(Part.Upload) << 32 | View;
			auto Found = UsedIndices.find(UsedKey);
			if (Found == UsedIndices.end())
			{
				std::array<uint64, 4> Used{};
				const int Per = TexelsPerUnit(Page.Depth);
				for (const FBeetleTexturePart& Held : BeetleTextureParts(Vram, WholePage(View)))
				{
					if (Held.Upload != Part.Upload)
					{
						continue;
					}
					for (int V = Held.V; V < Held.V + Held.Height && V < 256; ++V)
					{
						for (int U = Held.U; U < Held.U + Held.Width && U < 256; ++U)
						{
							const uint16 Word = Vram.TexelAt(Page.X + U / Per, Page.Y + V);
							const int Index = Per == 2 ? (Word >> ((U & 1) * 8) & 255) : (Word >> ((U & 3) * 4) & 15);
							Used[static_cast<std::size_t>(Index >> 6)] |= 1ull << (Index & 63);
						}
					}
				}
				Found = UsedIndices.emplace(UsedKey, Used).first;
			}
			uint64 Hash = 1469598103934665603ull;
			const auto Fold = [&Hash](uint64 Value) { Hash = (Hash ^ Value) * 1099511628211ull; };
			Fold(Part.Upload);
			Fold(static_cast<uint64>(Page.Depth));
			for (int Index = 0; Index < 256; ++Index)
			{
				if ((Found->second[static_cast<std::size_t>(Index >> 6)] >> (Index & 63) & 1) != 0)
				{
					Fold(static_cast<uint64>(Index) << 16 | Vram.TexelAt(Clut.X + Index, Clut.Y));
				}
			}
			return Hash | 1;
		}

		/** The pack's picture of an upload's part through View: by its own names, or one found through a palette agreeing on its colours; 0 none. */
		uint64 PictureName(const FVram& Vram, uint32 View, const FBeetleTexturePart& Part, bool bByContent = false) const
		{
			for (const uint32 Palette : {Part.Palette, Part.ReducedPalette})
			{
				if (InPack(PackKey(Part.Upload, Palette)) != nullptr)
				{
					if (const uint64 Same = UsedColoursKey(Vram, View, Part))
					{
						SamePalettePictures.emplace(Same, PackKey(Part.Upload, Palette));
					}
					return PackKey(Part.Upload, Palette);
				}
			}
			const uint64 Same = UsedColoursKey(Vram, View, Part);
			const auto Found = Same != 0 ? SamePalettePictures.find(Same) : SamePalettePictures.end();
			if (Found != SamePalettePictures.end())
			{
				return Found->second;
			}
			return bByContent ? AliasName(Vram, View, Part) : 0;
		}

		/**
		 * The pack's pictures whose original texels are known (SetAliasIndex: the user's extracted parts and Beetle's dumps,
		 * tools/sprite_alias_index.py), by size: what an upload the pack has no picture of is compared with, as the user's
		 * own pack session aliases a part the game uploads altered (xeno_sprites/tools/alias_dump_parts.py: same size,
		 * the colours of the texels opaque in both equal, the texels opaque in one only at most max(2, 5 %) of them).
		 */
		struct FAliasEntry
		{
			uint64 Key = 0;
			std::vector<uint16> Texels;
		};
		std::unordered_map<uint32, std::vector<FAliasEntry>> AliasBySize;
		/** What was found for an upload (by its pack key): the picture's key or 0, and how far the best candidate was. */
		struct FAliasFound
		{
			uint64 Key = 0, Best = 0;
			int Conflicts = -1, Edges = -1, Texels = 0;
			/** The texels opaque in the game's copy only (u | v << 16): FHdHit::Added. */
			std::vector<uint32> Added;
		};
		mutable std::unordered_map<uint64, FAliasFound> AliasFound;
		bool bAliasOn = false;
		/** XENO_ALIAS_REPORT=<file>: each upload compared, once, with its best candidate and the measures (appended). */
		std::FILE* AliasReport = nullptr;

		/** The upload's texels through the view's CLUT: 0 transparent, else 0x8000 | its 15-bit colour (the index's form). */
		bool UploadTexels(const FVram& Vram, uint32 View, const FBeetleTexturePart& Part, int& Wide, int& High, std::vector<uint16>& Out) const
		{
			const FTexturePage Page = TextureViewPage(View);
			if (Page.Y >= FVram::Height)
			{
				return false;
			}
			const FClutPosition Clut = TextureViewClut(View);
			const int Per = TexelsPerUnit(Page.Depth);
			for (const FBeetleTexturePart& Held : BeetleTextureParts(Vram, WholePage(View)))
			{
				if (Held.Upload != Part.Upload || Held.UploadUnitsWide != Part.UploadUnitsWide || Held.UploadUnitsHigh != Part.UploadUnitsHigh)
				{
					continue;
				}
				// Where the upload begins in the page (its part may begin inside it).
				const int U0 = Held.U - Held.FromU, V0 = Held.V - Held.FromV;
				Wide = Part.UploadUnitsWide * Per;
				High = Part.UploadUnitsHigh;
				Out.assign(static_cast<std::size_t>(Wide * High), 0);
				for (int V = 0; V < High; ++V)
				{
					for (int U = 0; U < Wide; ++U)
					{
						const int PageU = U0 + U;
						const uint16 Word = Vram.TexelAt(Page.X + (PageU >= 0 ? PageU / Per : -1), Page.Y + V0 + V);
						const uint16 Colour = Per == 4 ? Vram.TexelAt(Clut.X + (Word >> ((PageU & 3) * 4) & 15), Clut.Y)
							: Per == 2 ? Vram.TexelAt(Clut.X + (Word >> ((PageU & 1) * 8) & 255), Clut.Y) : Word;
						Out[static_cast<std::size_t>(V * Wide + U)] = Colour == 0 ? uint16{0} : static_cast<uint16>(0x8000 | (Colour & 0x7FFF));
					}
				}
				return true;
			}
			return false;
		}

		/**
		 * The picture of a sprite piece's own texels found by content, when neither its upload's names nor its drawn
		 * rectangle's are in the pack (a piece of a sheet uploaded whole or in strips, whose pictures are named by the
		 * pieces' rectangles): the drawn rectangle (RectHit's units) and then the piece's texels exactly, each compared as
		 * AliasName compares an upload. Placed in the picture as RectHit places it.
		 */
		FHdHit RegionAlias(const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, int MinU, int MinV, int Wide, int High) const
		{
			FHdHit Hit;
			if (!bAliasOn || Page.Y >= FVram::Rows)
			{
				return Hit;
			}
			const int Per = TexelsPerUnit(Page.Depth);
			// The palette's name as Beetle's (the CLUT's 16 or 256 colours).
			std::vector<uint16> Colours(Per == 4 ? 16 : Per == 2 ? 256 : 0);
			for (std::size_t Colour = 0; Colour < Colours.size(); ++Colour)
			{
				Colours[Colour] = Vram.TexelAt(Clut.X + static_cast<int>(Colour), Clut.Y);
			}
			const uint32 Palette = Colours.empty() ? 0u : Crc32OfUnits(Colours);
			// The drawn rectangle (whole units, a row less: the user's core's), then the piece's texels as they are.
			const int X0 = MinU / Per;
			const int Words = (MinU + Wide + 1) / Per - X0;
			const std::array<std::array<int, 4>, 2> Regions{{{X0 * Per, MinV, Words * Per, High - 1}, {MinU, MinV, Wide, High}}};
			for (std::size_t Which = 0; Which < Regions.size(); ++Which)
			{
				const auto& [U0, V0, RegionWide, RegionHigh] = Regions[Which];
				if (RegionWide <= 0 || RegionHigh <= 0 || U0 + RegionWide > 256 || V0 + RegionHigh > 256)
				{
					continue;
				}
				std::vector<uint16> Texels(static_cast<std::size_t>(RegionWide * RegionHigh));
				for (int V = 0; V < RegionHigh; ++V)
				{
					for (int U = 0; U < RegionWide; ++U)
					{
						const int PageU = U0 + U;
						const uint16 Word = Vram.TexelAt(Page.X + PageU / Per, Page.Y + V0 + V);
						const uint16 Colour = Per == 4 ? Vram.TexelAt(Clut.X + (Word >> ((PageU & 3) * 4) & 15), Clut.Y)
							: Per == 2 ? Vram.TexelAt(Clut.X + (Word >> ((PageU & 1) * 8) & 255), Clut.Y) : Word;
						Texels[static_cast<std::size_t>(V * RegionWide + U)] = Colour == 0 ? uint16{0} : static_cast<uint16>(0x8000 | (Colour & 0x7FFF));
					}
				}
				const uint64 Own = static_cast<uint64>(Crc32OfUnits(Texels, Palette)) << 32 | static_cast<uint64>(RegionWide) << 16 | static_cast<uint64>(RegionHigh);
				const char* What = Page.Y >= FVram::Height ? (Which == 0 ? "port-rect" : "port-piece") : (Which == 0 ? "region-rect" : "region-piece");
				const uint64 Key = MatchByContent(Own, Palette, Texels, RegionWide, RegionHigh, What);
				if (const uint8* Kind = Key != 0 ? InPack(Key) : nullptr)
				{
					Hit.Kind = FHdHit::Rect;
					Hit.Texture = PathOf(Key, *Kind);
					Hit.AddU = static_cast<float>(-U0);
					Hit.AddV = static_cast<float>(-V0);
					Hit.Wide = static_cast<float>(RegionWide);
					Hit.High = static_cast<float>(RegionHigh);
					Hit.Added = AliasFound[Own].Added;
					return Hit;
				}
			}
			return Hit;
		}

		/** The index's picture of these texels (AliasName's rule), remembered by Own; 0 none. */
		uint64 MatchByContent(uint64 Own, uint32 Palette, const std::vector<uint16>& Texels, int Wide, int High, const char* What) const
		{
			const auto Known = AliasFound.find(Own);
			if (Known != AliasFound.end())
			{
				return Known->second.Key;
			}
			FAliasFound Found;
			Found.Texels = Wide * High;
			const auto Bucket = AliasBySize.find(static_cast<uint32>(Wide) << 16 | static_cast<uint32>(High));
			if (Bucket != AliasBySize.end())
			{
				// The best candidate: fewest opaque texels of another colour, then fewest texels opaque in one only.
				for (const FAliasEntry& Entry : Bucket->second)
				{
					// The user's rule takes a part of the same palette only (alias_dump_parts.py: by (palette, w, h)).
					if (static_cast<uint32>(Entry.Key) != Palette)
					{
						continue;
					}
					int Conflicts = 0, Edges = 0;
					for (std::size_t Texel = 0; Texel < Texels.size() && Conflicts <= Found.Conflicts + 64; ++Texel)
					{
						const uint16 A = Texels[Texel], B = Entry.Texels[Texel];
						if ((A != 0) != (B != 0))
						{
							++Edges;
						}
						else if (A != 0 && A != B)
						{
							// The user's tolerance: 8 of 255 a channel, one step of 31.
							const int Dr = std::abs((A & 31) - (B & 31)), Dg = std::abs((A >> 5 & 31) - (B >> 5 & 31)), Db = std::abs((A >> 10 & 31) - (B >> 10 & 31));
							Conflicts += Dr > 1 || Dg > 1 || Db > 1 ? 1 : 0;
						}
					}
					if (Found.Best == 0 || Conflicts < Found.Conflicts || (Conflicts == Found.Conflicts && Edges < Found.Edges))
					{
						Found.Best = Entry.Key;
						Found.Conflicts = Conflicts;
						Found.Edges = Edges;
					}
				}
				if (Found.Best != 0 && Found.Conflicts == 0 && Found.Edges <= std::max(2, Found.Texels / 20) && InPack(Found.Best) != nullptr)
				{
					Found.Key = Found.Best;
					for (const FAliasEntry& Entry : Bucket->second)
					{
						if (Entry.Key != Found.Key)
						{
							continue;
						}
						for (std::size_t Texel = 0; Texel < Texels.size(); ++Texel)
						{
							if (Texels[Texel] != 0 && Entry.Texels[Texel] == 0)
							{
								Found.Added.push_back(static_cast<uint32>(Texel % static_cast<std::size_t>(Wide)) | static_cast<uint32>(Texel / static_cast<std::size_t>(Wide)) << 16);
							}
						}
						break;
					}
				}
			}
			if (AliasReport != nullptr)
			{
				// The texels compared, in the index's form (for the substitution sheets: tools/sprite_alias_sheet.py).
				std::string Hex;
				Hex.reserve(Texels.size() * 4);
				for (const uint16 Texel : Texels)
				{
					char Unit[8];
					std::snprintf(Unit, sizeof(Unit), "%04x", Texel);
					Hex += Unit;
				}
				std::fprintf(AliasReport, "%s %x,%d,%d,%s,%d,%d,%d,%x,%s\n", What, static_cast<uint32>(Own >> 32), Wide, High,
					Found.Best != 0 ? BeetleTextureFileName({static_cast<uint32>(Found.Best >> 32), static_cast<uint32>(Found.Best)}).c_str() : "-",
					Found.Conflicts, Found.Edges, Found.Key != 0 ? 1 : 0, Palette, Wide * High <= 4096 ? Hex.c_str() : "");
				std::fflush(AliasReport);
			}
			return AliasFound.emplace(Own, Found).first->second.Key;
		}

		uint64 AliasName(const FVram& Vram, uint32 View, const FBeetleTexturePart& Part) const
		{
			if (!bAliasOn)
			{
				return 0;
			}
			const uint64 Own = PackKey(Part.Upload, Part.Palette);
			const auto Known = AliasFound.find(Own);
			if (Known != AliasFound.end())
			{
				return Known->second.Key;
			}
			int Wide = 0, High = 0;
			std::vector<uint16> Texels;
			if (!UploadTexels(Vram, View, Part, Wide, High, Texels))
			{
				return AliasFound.emplace(Own, FAliasFound{}).first->second.Key;
			}
			return MatchByContent(Own, Part.Palette, Texels, Wide, High, BeetleTextureFileName({Part.Upload, Part.Palette}).c_str());
		}

		/** Resolve, remembered by region (scenery for the map's life, the rest for the frame). */
		const FHdHit& Cached(std::unordered_map<uint64, FHdHit>& Hits, const FVram& Vram, const FTexturePage& Page, const FClutPosition& Clut, int MinU,
			int MinV, int Wide, int High, bool bSprite)
		{
			const uint64 Key = static_cast<uint64>(PackTextureView(Page, Clut)) | static_cast<uint64>(MinU & 255) << 32
				| static_cast<uint64>(MinV & 255) << 40 | static_cast<uint64>((Wide - 1) & 255) << 48 | static_cast<uint64>((High - 1) & 255) << 56;
			const auto Found = Hits.find(Key);
			if (Found != Hits.end())
			{
				return Found->second;
			}
			return Hits.emplace(Key, Resolve(Vram, Page, Clut, MinU, MinV, Wide, High, bSprite)).first->second;
		}

		/**
		 * Puts a textured primitive into its surface: the pack's picture when it has one, with the corners' texels moved
		 * into it, or VRAM's texels. The corners carry the game's own texel coordinates (for a sprite's piece, PushViewQuad's).
		 */
		void PushTextured(FCollector& Into, std::unordered_map<uint64, FHdHit>& Hits, const FVram& Vram, EBlend Blend, std::array<FCorner, 4> Corners,
			int Count, FLook Look, const FTexturePage& Page, const FClutPosition& Clut, bool bOnePast, bool bSprite, const std::array<float, 3>* Facing,
			ETally Tally = ETally::None, bool bEitherEdge = false)
		{
			float MinU = 1e9f, MinV = 1e9f, MaxU = -1e9f, MaxV = -1e9f;
			for (int Corner = 0; Corner < Count; ++Corner)
			{
				MinU = std::min(MinU, Corners[static_cast<std::size_t>(Corner)].U);
				MinV = std::min(MinV, Corners[static_cast<std::size_t>(Corner)].V);
				MaxU = std::max(MaxU, Corners[static_cast<std::size_t>(Corner)].U);
				MaxV = std::max(MaxV, Corners[static_cast<std::size_t>(Corner)].V);
			}
			const int U0 = static_cast<int>(std::floor(MinU)), V0 = static_cast<int>(std::floor(MinV));
			const int Wide = static_cast<int>(std::ceil(MaxU)) - U0 + (bOnePast ? 0 : 1);
			const int High = static_cast<int>(std::ceil(MaxV)) - V0 + (bOnePast ? 0 : 1);
			if (bLogSpritePalettes && Tally == ETally::Sprite)
			{
				NoteSpritePalettes(Vram, Page, Clut, U0, V0, Wide, High);
			}
			const FHdHit* Hit = Options.bHd && !Pack.empty() && U0 >= 0 && V0 >= 0 && U0 < 256 && V0 < 256
				? &Cached(Hits, Vram, Page, Clut, U0, V0, Wide, High, bSprite) : nullptr;
			// A 2D primitive without its texel range may end at its last texel (a polygon's corners) or one past it (a sprite's
			// right and bottom edges): the region to the last texel reaches a texel past the upload in the second case, so the
			// one without that texel is tried too. The picture's place does not change (it counts from the region's first
			// texel), and the clamp below then runs to one past the last texel, the far edge of the texels drawn.
			const bool bExclusive = bEitherEdge && !bOnePast;
			const int TallyWide = bExclusive ? std::max(1, Wide - 1) : Wide, TallyHigh = bExclusive ? std::max(1, High - 1) : High;
			if (Hit != nullptr && Hit->Kind == FHdHit::None && bExclusive)
			{
				Hit = &Cached(Hits, Vram, Page, Clut, U0, V0, TallyWide, TallyHigh, bSprite);
			}
			// A picture the display has not loaded yet: VRAM's texels until it has (asked for meanwhile).
			if (Hit != nullptr && Hit->Kind != FHdHit::None && !IsReady(Hit->Texture))
			{
				DumpPath = "waiting";
				if (Report != nullptr)
				{
					FReportMiss Miss;
					Miss.Kind = Tally == ETally::Sprite ? "sprite" : Tally == ETally::Screen ? "2D" : "other";
					Miss.Name = std::filesystem::path(Hit->Texture).filename().string();
					Miss.Why = "waiting: its pack picture was still loading (drawn from VRAM this frame)";
					Miss.Who = Report->Who;
					Report->Misses.push_back(std::move(Miss));
				}
				++FromVram;
				++Waiting;
				if (Tally == ETally::Sprite)
				{
					++SpritePieces;
					++SpriteVram;
					++SpriteWaiting;
				}
				ScreenWaiting += Tally == ETally::Screen ? 1 : 0;
				PushPrimitive(Into.Get(Blend, {}), Corners, Count, Look, Facing);
				return;
			}
			if (Hit == nullptr || Hit->Kind == FHdHit::None)
			{
				// A quad whose texels run along its edges (a sprite's piece, a portrait or window of the 2D layer) can be cut.
				const bool bAxisAligned = Count == 4 && Corners[0].U == Corners[2].U && Corners[1].U == Corners[3].U && Corners[0].V == Corners[1].V
					&& Corners[2].V == Corners[3].V;
				std::vector<FBeetleTexturePart> Drawn;
				bool bGaps = false;
				if (Hit != nullptr && bAxisAligned
					&& PushSplit(Into, Vram, Blend, Corners, Look, Page, Clut, U0, V0, Wide, High, MinU, MinV, MaxU, MaxV, Facing, Drawn, bGaps))
				{
					++HdSplit;
					DumpPath = "split " + std::to_string(Drawn.size()) + (bGaps ? " gaps" : "");
					if (Tally != ETally::None || Report != nullptr)
					{
						// Whole from the pack when every part drawn found its picture.
						const uint32 View = PackTextureView(Page, Clut);
							const bool bWhole =
								std::all_of(Drawn.begin(), Drawn.end(), [&](const FBeetleTexturePart& Part) { return HasPictureThrough(Vram, View, Part, true); });
						if (!bWhole)
						{
							// A frame report notes the untallied too (TallyMiss is the tallies' own, so not for them).
							const int Lacking = Tally != ETally::None ? TallyMiss(Tally, Drawn)
								: static_cast<int>(std::count_if(Drawn.begin(), Drawn.end(), [&](const FBeetleTexturePart& Part) { return !HasPicture(Part); }));
							LogMiss(Tally, "partial", Page, Clut, U0, V0, Wide, High, Corners, Count, Drawn, Lacking, &Vram);
						}
						if (Tally == ETally::Sprite)
						{
							++SpritePieces;
							++(bWhole ? SpriteHd : SpritePartial);
							SpriteSplitGaps += bGaps ? 1 : 0;
							SpriteWaiting += bPartWaiting ? 1 : 0;
						}
						else if (Tally == ETally::Screen)
						{
							ScreenHd += bWhole ? 1 : 0;
							ScreenWaiting += bPartWaiting ? 1 : 0;
						}
					}
					return;
				}
				++FromVram;
				DumpPath = Hit == nullptr ? "vram (no lookup)" : "vram";
				PushPrimitive(Into.Get(Blend, {}), Corners, Count, Look, Facing);
				if (Tally != ETally::None)
				{
					// Uploads under the texels surely drawn (without the edge texel in doubt).
					const std::vector<FBeetleTexturePart> Parts = PartsUnder(Vram, Page, Clut, U0, V0, TallyWide, TallyHigh);
					LogMiss(Tally, "vram", Page, Clut, U0, V0, TallyWide, TallyHigh, Corners, Count, Parts, TallyMiss(Tally, Parts), &Vram);
					if (Tally == ETally::Sprite)
					{
						++SpritePieces;
						++SpriteVram;
					}
				}
				else if (Report != nullptr && Hit != nullptr)
				{
					// A frame report notes the untallied too (particles, effects, the world map's pieces), without the tallies.
					const std::vector<FBeetleTexturePart> Parts = PartsUnder(Vram, Page, Clut, U0, V0, TallyWide, TallyHigh);
					const int Lacking = static_cast<int>(std::count_if(Parts.begin(), Parts.end(), [&](const FBeetleTexturePart& Part) { return !HasPicture(Part); }));
					LogMiss(Tally, "vram", Page, Clut, U0, V0, TallyWide, TallyHigh, Corners, Count, Parts, Lacking, &Vram);
				}
				return;
			}
			++(Hit->Kind == FHdHit::Upload ? HdUpload : HdRect);
			if (Dumping2D())
			{
				char Text[160];
				std::snprintf(Text, sizeof(Text), "pack-%s %s add %g,%g size %gx%g", Hit->Kind == FHdHit::Upload ? "upload" : "rect", Hit->Texture.c_str(), Hit->AddU,
					Hit->AddV, Hit->Wide, Hit->High);
				DumpPath = Text;
			}
			// The picture holds the page's texels from (-AddU, -AddV) on, Wide x High of them.
			const float HeldU0 = -Hit->AddU, HeldU1 = Hit->Wide - Hit->AddU, HeldV0 = -Hit->AddV, HeldV1 = Hit->High - Hit->AddV;
			if (Blend != EBlend::Opaque)
			{
				NoteSemiPicture(Hit->Texture, Vram, Page, Clut, static_cast<int>(HeldU0), static_cast<int>(HeldV0), static_cast<int>(Hit->Wide), static_cast<int>(Hit->High));
				NoteRim(Hit->Texture, static_cast<int>(std::floor(MinU)), static_cast<int>(std::floor(MinV)),
					std::max(static_cast<int>(std::floor(MinU)), static_cast<int>(std::ceil(MaxU)) - 1),
					std::max(static_cast<int>(std::floor(MinV)), static_cast<int>(std::ceil(MaxV)) - 1));
			}
			// The texels a primitive shows run from its first coordinate up to its last (the far edge's, MaxU, MaxV, not
			// reached). A picture may hold fewer: a drawn rectangle's picture (RectHit, the user's core's formula) can end a
			// column or two before a piece's last texels, which a clamp would smear or leave as a hole (a stripe down the piece).
			// Each texel comes from where it is: what the picture holds from it, the rest from VRAM, as PushSplit draws
			// texels no picture holds.
			const bool bAxisAligned = Count == 4 && Corners[0].U == Corners[2].U && Corners[1].U == Corners[3].U && Corners[0].V == Corners[1].V
				&& Corners[2].V == Corners[3].V;
			const float Slack = 1e-3f;
			if (!WithoutTask8() && bAxisAligned
				&& (MinU < HeldU0 - Slack || MaxU > HeldU1 + Slack || MinV < HeldV0 - Slack || MaxV > HeldV1 + Slack))
			{
				++HdBeyond;
				DumpPath += " beyond its picture";
				if (Tally == ETally::Sprite)
				{
					++SpritePieces;
					++SpritePartial;
					++SpriteBeyond;
					if (bLogSpritePalettes)
					{
						++SpriteMisses[{"beyond", std::filesystem::path(Hit->Texture).stem().string()}];
					}
				}
				ScreenBeyond += Tally == ETally::Screen ? 1 : 0;
				// The user's core draws such a piece wholly from its picture: a tap past the picture's texels is clamped to
				// them, its edge texel replicated (beetle_src/rhi/shaders_vulkan/hdtextures.h, sample_hd_texture_nearest, its
				// xeno patch: a tap outside the texture's texel rect used to fall back to the native texel - thin native seams
				// along sprite parts' edges). The same here: the shader keeps its taps inside Clamp, the texels the picture
				// holds. XENO_BEYOND_VRAM=1: those texels from VRAM instead (15b99a7's rule, for comparisons).
				const float ClampU0 = std::max(MinU, HeldU0), ClampU1 = std::min(MaxU, HeldU1);
				const float ClampV0 = std::max(MinV, HeldV0), ClampV1 = std::min(MaxV, HeldV1);
				static const bool bBeyondVram = std::getenv("XENO_BEYOND_VRAM") != nullptr;
				if (!bBeyondVram && ClampU0 <= ClampU1 && ClampV0 <= ClampV1)
				{
					PushAdded(Into, *Hit, Blend, Corners, Look, Facing, MinU, MinV, MaxU, MaxV);
					if (Tally == ETally::Sprite)
					{
						--SpritePartial;
						++SpriteHd;
					}
					ScreenHd += Tally == ETally::Screen ? 1 : 0;
					Look.Clamp = {(ClampU0 + Hit->AddU) / Hit->Wide, (ClampV0 + Hit->AddV) / Hit->High, (ClampU1 + Hit->AddU) / Hit->Wide,
						(ClampV1 + Hit->AddV) / Hit->High};
					for (int Corner = 0; Corner < Count; ++Corner)
					{
						FCorner& At = Corners[static_cast<std::size_t>(Corner)];
						At.U = (At.U + Hit->AddU) / Hit->Wide;
						At.V = (At.V + Hit->AddV) / Hit->High;
					}
					PushPrimitive(Into.Get(Blend, Hit->Texture), Corners, Count, Look, Facing);
					return;
				}
				const std::vector<FBand> AcrossU = Bands(MinU, MaxU, HeldU0, HeldU1), AcrossV = Bands(MinV, MaxV, HeldV0, HeldV1);
				for (const FBand& BandV : AcrossV)
				{
					for (const FBand& BandU : AcrossU)
					{
						std::array<FCorner, 4> Quad = SubQuad(Corners, BandU.From, BandU.To, BandV.From, BandV.To);
						if (!BandU.bHeld || !BandV.bHeld)
						{
							PushPrimitive(Into.Get(Blend, {}), Quad, 4, Look, Facing);
							continue;
						}
						FLook InPicture = Look;
						InPicture.Clamp = {(BandU.From + Hit->AddU) / Hit->Wide, (BandV.From + Hit->AddV) / Hit->High, (BandU.To + Hit->AddU) / Hit->Wide,
							(BandV.To + Hit->AddV) / Hit->High};
						for (FCorner& At : Quad)
						{
							At.U = (At.U + Hit->AddU) / Hit->Wide;
							At.V = (At.V + Hit->AddV) / Hit->High;
						}
						PushPrimitive(Into.Get(Blend, Hit->Texture), Quad, 4, InPicture, Facing);
					}
				}
				return;
			}
			if (Tally == ETally::Sprite)
			{
				++SpritePieces;
				++SpriteHd;
			}
			else if (Tally == ETally::Screen)
			{
				++ScreenHd;
			}
			PushAdded(Into, *Hit, Blend, Corners, Look, Facing, MinU, MinV, MaxU, MaxV);
			// The picture holds the piece's neighbours too: the shader keeps its taps inside the piece (as the user's core does).
			Look.Clamp = {(MinU + Hit->AddU) / Hit->Wide, (MinV + Hit->AddV) / Hit->High, (MaxU + Hit->AddU) / Hit->Wide, (MaxV + Hit->AddV) / Hit->High};
			for (int Corner = 0; Corner < Count; ++Corner)
			{
				FCorner& At = Corners[static_cast<std::size_t>(Corner)];
				At.U = (At.U + Hit->AddU) / Hit->Wide;
				At.V = (At.V + Hit->AddV) / Hit->High;
			}
			PushPrimitive(Into.Get(Blend, Hit->Texture), Corners, Count, Look, Facing);
		}

		/**
		 * Under a picture found by content: each texel the game draws that the picture's original lacked (FHdHit::Added),
		 * from VRAM, so the picture shows no hole there (the user's pack session fills such texels in its copies,
		 * alias_dump_parts.py fill_gaps). In the world a hair behind the picture; on the 2D layer before it.
		 */
		void PushAdded(FCollector& Into, const FHdHit& Hit, EBlend Blend, const std::array<FCorner, 4>& Corners, const FLook& Look,
			const std::array<float, 3>* Facing, float MinU, float MinV, float MaxU, float MaxV)
		{
			for (const uint32 At : Hit.Added)
			{
				const float U = static_cast<float>(At & 0xFFFF) - Hit.AddU, V = static_cast<float>(At >> 16) - Hit.AddV;
				const float Ua = std::max(U, MinU), Ub = std::min(U + 1.0f, MaxU), Va = std::max(V, MinV), Vb = std::min(V + 1.0f, MaxV);
				if (Ub <= Ua || Vb <= Va)
				{
					continue;
				}
				std::array<FCorner, 4> Quad = SubQuad(Corners, Ua, Ub, Va, Vb);
				if (Facing != nullptr)
				{
					for (FCorner& Corner : Quad)
					{
						for (float& Axis : Corner.Pos)
						{
							Axis *= 1.0005f;
						}
					}
				}
				PushPrimitive(Into.Get(Blend, {}), Quad, 4, Look, Facing);
			}
		}

		/** A stretch of texel coordinates along one axis, and whether a picture holds its texels. */
		struct FBand
		{
			float From = 0.0f, To = 0.0f;
			bool bHeld = false;
		};

		/**
		 * Low to High cut where a picture's texels (HeldLow to HeldHigh) begin and end: the stretches before, inside and
		 * after. A constant coordinate (Low = High: a piece one texel wide) is one stretch, held or not.
		 */
		static std::vector<FBand> Bands(float Low, float High, float HeldLow, float HeldHigh)
		{
			std::vector<FBand> Out;
			if (High - Low < 1e-6f)
			{
				Out.push_back({Low, High, Low >= HeldLow && Low < HeldHigh});
				return Out;
			}
			const float A = std::clamp(HeldLow, Low, High), B = std::clamp(HeldHigh, Low, High);
			if (A > Low)
			{
				Out.push_back({Low, A, false});
			}
			if (B > A)
			{
				Out.push_back({A, B, true});
			}
			if (High > B)
			{
				Out.push_back({B, High, false});
			}
			return Out;
		}

		/**
		 * The part of an axis-aligned quad (corners 0 and 2 at one u, 1 and 3 at the other; 0 and 1 at one v, 2 and 3 at the
		 * other) whose texel coordinates run from Ua to Ub and Va to Vb: its corners where those coordinates lie on it
		 * (places and colours in proportion), as the GPU interpolates the coordinates across the quad.
		 */
		static std::array<FCorner, 4> SubQuad(const std::array<FCorner, 4>& Corners, float Ua, float Ub, float Va, float Vb)
		{
			const float AlongU = Corners[1].U - Corners[0].U, AlongV = Corners[2].V - Corners[0].V;
			std::array<FCorner, 4> Quad{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				const bool bFar = (Corner & 1) != 0, bLower = (Corner & 2) != 0;
				// Corner 1's side of the quad is the far end of its u's way (down it for a quad mirrored in its texels).
				const float U = (bFar == (AlongU >= 0.0f)) ? Ub : Ua, V = (bLower == (AlongV >= 0.0f)) ? Vb : Va;
				const float S = AlongU != 0.0f ? (U - Corners[0].U) / AlongU : (bFar ? 1.0f : 0.0f);
				const float T = AlongV != 0.0f ? (V - Corners[0].V) / AlongV : (bLower ? 1.0f : 0.0f);
				const std::array<float, 4> Weight{(1 - S) * (1 - T), S * (1 - T), (1 - S) * T, S * T};
				for (std::size_t Axis = 0; Axis < 3; ++Axis)
				{
					float Sum = 0.0f;
					for (std::size_t From = 0; From < 4; ++From)
					{
						Sum += Corners[From].Pos[Axis] * Weight[From];
					}
					Quad[Corner].Pos[Axis] = Sum;
				}
				for (std::size_t Channel = 0; Channel < 3; ++Channel)
				{
					float Sum = 0.0f;
					for (std::size_t From = 0; From < 4; ++From)
					{
						Sum += static_cast<float>(Corners[From].Color[Channel]) * Weight[From];
					}
					Quad[Corner].Color[Channel] = static_cast<uint8_t>(std::clamp(std::lround(Sum), 0L, 255L));
				}
				Quad[Corner].U = U;
				Quad[Corner].V = V;
			}
			return Quad;
		}

		/**
		 * A sprite's piece whose texels lie in more than one upload (an NPC's sprites loaded in strips of rows): cut along
		 * the uploads into quads, each drawn from its upload's picture where the pack has one (VRAM's texels where it has
		 * none), as Beetle takes each texel from the upload it lies in. The corners carry the game's own texel coordinates.
		 * False when the piece lies in one upload or none. Drawn gets the parts drawn; bGaps whether some of the piece's
		 * texels lie in no upload (those are not drawn at all).
		 */
		/** Whether the last PushSplit drew a part from VRAM only because its picture is not loaded yet. */
		bool bPartWaiting = false;

		bool PushSplit(FCollector& Into, const FVram& Vram, EBlend Blend, const std::array<FCorner, 4>& Corners, const FLook& Look, const FTexturePage& Page,
			const FClutPosition& Clut, int U0, int V0, int Wide, int High, float MinU, float MinV, float MaxU, float MaxV, const std::array<float, 3>* Facing,
			std::vector<FBeetleTexturePart>& Drawn, bool& bGaps)
		{
			bPartWaiting = false;
			FTextureRegion Region;
			Region.View = PackTextureView(Page, Clut);
			Region.U = static_cast<uint8>(U0);
			Region.V = static_cast<uint8>(V0);
			Region.Width = static_cast<uint16>(std::clamp(Wide, 1, 256 - U0));
			Region.Height = static_cast<uint16>(std::clamp(High, 1, 256 - V0));
			const std::vector<FBeetleTexturePart> Parts = BeetleTextureParts(Vram, Region);
			const float SpanU = MaxU - MinU, SpanV = MaxV - MinV;
			const float AlongU = Corners[1].U - Corners[0].U, AlongV = Corners[2].V - Corners[0].V;
			// A piece one texel wide (or high) keeps one column (row) for its whole quad once its last texel is its first: it is
			// cut along the other axis only, its constant coordinate kept, and places across it come from the corners' order.
			const bool bFlatU = SpanU < 1.0f || AlongU == 0.0f, bFlatV = SpanV < 1.0f || AlongV == 0.0f;
			if (Parts.size() < 2 || (bFlatU && bFlatV))
			{
				return false;
			}
			const int Per = TexelsPerUnit(Page.Depth);
			// The texels the quad spans (each texel cell inside MinU..MaxU, MinV..MaxV), to see whether the parts cover them all.
			const int FirstU = static_cast<int>(std::floor(MinU)), FirstV = static_cast<int>(std::floor(MinV));
			const int SpanColumns = std::max(1, static_cast<int>(std::ceil(MaxU)) - FirstU), SpanRows = std::max(1, static_cast<int>(std::ceil(MaxV)) - FirstV);
			std::vector<uint8> Covered(static_cast<std::size_t>(SpanColumns * SpanRows), 0);
			for (const FBeetleTexturePart& Part : Parts)
			{
				const float Ua = std::max(MinU, static_cast<float>(U0 + Part.U)), Ub = std::min(MaxU, static_cast<float>(U0 + Part.U + Part.Width));
				const float Va = std::max(MinV, static_cast<float>(V0 + Part.V)), Vb = std::min(MaxV, static_cast<float>(V0 + Part.V + Part.Height));
				// Along a flat axis the part must hold the piece's one column (row); along the other it must overlap the span.
				const bool bHoldsU = bFlatU ? U0 + Part.U <= MinU && MinU < U0 + Part.U + Part.Width : Ub > Ua;
				const bool bHoldsV = bFlatV ? V0 + Part.V <= MinV && MinV < V0 + Part.V + Part.Height : Vb > Va;
				if (!bHoldsU || !bHoldsV)
				{
					continue;
				}
				Drawn.push_back(Part);
				for (int Row = std::max(0, V0 + Part.V - FirstV); Row < std::min(SpanRows, V0 + Part.V + Part.Height - FirstV); ++Row)
				{
					for (int Column = std::max(0, U0 + Part.U - FirstU); Column < std::min(SpanColumns, U0 + Part.U + Part.Width - FirstU); ++Column)
					{
						Covered[static_cast<std::size_t>(Row * SpanColumns + Column)] = 1;
					}
				}
				std::array<FCorner, 4> Quad{};
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					const bool bRight = (Corner & 1) != 0, bLower = (Corner & 2) != 0;
					const float U = bFlatU ? Corners[Corner & 1].U : bRight ? Ub : Ua, V = bFlatV ? Corners[Corner & 2].V : bLower ? Vb : Va;
					const float S = bFlatU ? (bRight ? 1.0f : 0.0f) : (U - Corners[0].U) / AlongU;
					const float T = bFlatV ? (bLower ? 1.0f : 0.0f) : (V - Corners[0].V) / AlongV;
					for (std::size_t Axis = 0; Axis < 3; ++Axis)
					{
						Quad[Corner].Pos[Axis] = Corners[0].Pos[Axis] * (1 - S) * (1 - T) + Corners[1].Pos[Axis] * S * (1 - T)
							+ Corners[2].Pos[Axis] * (1 - S) * T + Corners[3].Pos[Axis] * S * T;
					}
					Quad[Corner].Color = Corners[0].Color;
					Quad[Corner].U = U;
					Quad[Corner].V = V;
				}
				const uint64 Name = PictureName(Vram, Region.View, Part, true);
				const uint8* Kind = Name != 0 ? InPack(Name) : nullptr;
				if (Kind == nullptr || !IsReady(PathOf(Name, *Kind)))
				{
					Waiting += Kind != nullptr ? 1 : 0;
					bPartWaiting = bPartWaiting || Kind != nullptr;
					PushPrimitive(Into.Get(Blend, {}), Quad, 4, Look, Facing);
					continue;
				}
				const float PictureWide = static_cast<float>(Part.UploadUnitsWide * Per), PictureHigh = static_cast<float>(Part.UploadUnitsHigh);
				const float AddU = static_cast<float>(Part.FromU - (U0 + Part.U)), AddV = static_cast<float>(Part.FromV - (V0 + Part.V));
				if (Blend != EBlend::Opaque)
				{
					NoteSemiPicture(PathOf(Name, *Kind), Vram, Page, Clut, U0 + Part.U - Part.FromU, V0 + Part.V - Part.FromV, Part.UploadUnitsWide * Per, Part.UploadUnitsHigh);
					NoteRim(PathOf(Name, *Kind), static_cast<int>(std::floor(Ua)), static_cast<int>(std::floor(Va)),
						std::max(static_cast<int>(std::floor(Ua)), static_cast<int>(std::ceil(Ub)) - 1),
						std::max(static_cast<int>(std::floor(Va)), static_cast<int>(std::ceil(Vb)) - 1));
				}
				FLook InPicture = Look;
				InPicture.Clamp = {(Part.FromU) / PictureWide, (Part.FromV) / PictureHigh, (Part.FromU + Part.Width) / PictureWide,
					(Part.FromV + Part.Height) / PictureHigh};
				for (FCorner& Corner : Quad)
				{
					Corner.U = (Corner.U + AddU) / PictureWide;
					Corner.V = (Corner.V + AddV) / PictureHigh;
				}
				PushPrimitive(Into.Get(Blend, PathOf(Name, *Kind)), Quad, 4, InPicture, Facing);
			}
			bGaps = std::find(Covered.begin(), Covered.end(), uint8{0}) != Covered.end();
			return true;
		}

		/**
		 * A polygon of a model laid in a map's or a battle stage's scene: textured from the page with the pack's pictures
		 * laid in (its texels across 0-1, taps kept inside the polygon's texels) where the page has any, else from VRAM.
		 */
		void PushScenery(FCollector& Into, const FVram& Vram, std::array<FCorner, 4> Corners, int Count, FLook Look, bool bTextured,
			const FTexturePage& Page, const FClutPosition& Clut, EBlend Blend)
		{
			const uint32 PageView = PackTextureView(Page, Clut);
			const bool bPictures = bTextured && Options.bHd && !Pack.empty() && Page.Y < FVram::Height && PageState(Vram, PageView) != 0;
			// The page's picture of the pictures laid in now: each state its own (an animated palette's may change them).
			char Key[32];
			std::snprintf(Key, sizeof(Key), "page:%08x-%08x", PageView, bPictures ? PageState(Vram, PageView) : 0u);
			// XENO_DUMP_OBJECTS=1 (checks): each scenery/object polygon drawn onto the 2D layer (a battle's links over its fade
			// or HUD): its page, CLUT, texels, whether the page has pictures, and each upload under its texels with its name.
			static const bool bDumpObjects = std::getenv("XENO_DUMP_OBJECTS") != nullptr;
			// A frame report takes every one (the field's, the world map's, the arena's too), and notes the uploads under it
			// without their picture.
			if (Report != nullptr && bTextured)
			{
				const bool bWaiting = bPictures && !IsReady(Key);
				float MinU = 256.0f, MinV = 256.0f, MaxU = 0.0f, MaxV = 0.0f;
				for (int Corner = 0; Corner < Count; ++Corner)
				{
					MinU = std::min(MinU, Corners[static_cast<std::size_t>(Corner)].U);
					MinV = std::min(MinV, Corners[static_cast<std::size_t>(Corner)].V);
					MaxU = std::max(MaxU, Corners[static_cast<std::size_t>(Corner)].U);
					MaxV = std::max(MaxV, Corners[static_cast<std::size_t>(Corner)].V);
				}
				DumpPath = !Options.bHd || Pack.empty() ? "vram (no pack)" : Page.Y >= FVram::Height ? "vram (the port's rows)"
					: !bPictures ? "vram (no picture of any upload on its page)" : bWaiting ? "vram (waiting for its page)" : std::string("page ") + Key;
				if (Options.bHd && !Pack.empty())
				{
					const int U0 = static_cast<int>(MinU), V0 = static_cast<int>(MinV);
					const std::vector<FBeetleTexturePart> Parts = PartsUnder(Vram, Page, Clut, U0, V0, static_cast<int>(std::ceil(MaxU)) - U0 + 1,
						static_cast<int>(std::ceil(MaxV)) - V0 + 1);
					for (const FBeetleTexturePart& Part : Parts)
					{
						if (PictureName(Vram, PageView, Part) != 0)
						{
							if (bWaiting)
							{
								NoteReportPart("model", Page, U0, V0, Part, "waiting: its page with the pack's pictures was still loading");
							}
							continue;
						}
						std::string Why = bPictures ? "its page has pictures, this upload none: the original's texels scaled up"
							: "no upload on its page has a picture: drawn from VRAM";
						if (const int Others = OtherPalettes(Part); Others > 0)
						{
							Why += " (the pack has this upload under " + std::to_string(Others) + " other palette" + (Others > 1 ? "s" : "") + ")";
						}
						NoteReportPart("model", Page, U0, V0, Part, Why);
					}
					if (Parts.empty() && Page.Y >= FVram::Height)
					{
						FReportMiss Miss;
						Miss.Kind = "model";
						Miss.Name = "-";
						Miss.Why = "texels in the port's own rows of VRAM: no pack name";
						Miss.Who = Report->Who;
						Report->Misses.push_back(std::move(Miss));
					}
				}
			}
			else if (Report != nullptr)
			{
				DumpPath = "untextured";
			}
			if (((bDumpObjects && bBattleDrawing) || Report != nullptr) && bTextured)
			{
				float MinU = 256.0f, MinV = 256.0f, MaxU = 0.0f, MaxV = 0.0f;
				for (int Corner = 0; Corner < Count; ++Corner)
				{
					MinU = std::min(MinU, Corners[static_cast<std::size_t>(Corner)].U);
					MinV = std::min(MinV, Corners[static_cast<std::size_t>(Corner)].V);
					MaxU = std::max(MaxU, Corners[static_cast<std::size_t>(Corner)].U);
					MaxV = std::max(MaxV, Corners[static_cast<std::size_t>(Corner)].V);
				}
				Dump("object %s: corners %d page %d,%d depth %d clut %d,%d uv %g..%g,%g..%g blend %d pictures %d %s:", bBattleToScreen ? "over layers" : "scene", Count, Page.X, Page.Y,
					static_cast<int>(Page.Depth), Clut.X, Clut.Y, MinU, MaxU, MinV, MaxV, static_cast<int>(Blend), bPictures ? 1 : 0, Key);
				for (const FBeetleTexturePart& Part : PartsUnder(Vram, Page, Clut, static_cast<int>(MinU), static_cast<int>(MinV),
						 static_cast<int>(std::ceil(MaxU)) - static_cast<int>(MinU) + 1, static_cast<int>(std::ceil(MaxV)) - static_cast<int>(MinV) + 1))
				{
					Dump(" [%s at %d,%d %dx%d of %dx%d units%s]", BeetleTextureFileName({Part.Upload, Part.Palette}).c_str(), Part.U, Part.V, Part.Width,
						Part.Height, Part.UploadUnitsWide, Part.UploadUnitsHigh, PictureName(Vram, PageView, Part) != 0 ? " in-pack" : "");
				}
				if (Report != nullptr)
				{
					// The report's own addition: what the polygon is of, and the path its texels took.
					Dump(" (%s) -> %s", Report->Who.c_str(), DumpPath.c_str());
				}
				Dump("\n");
			}
			// A page the display has not built yet is drawn from VRAM until it has (asked for meanwhile).
			if (bPictures && !IsReady(Key))
			{
				++Waiting;
				++FromVram;
				++SceneryVram;
				PushPrimitive(Into.Get(Blend, {}), Corners, Count, Look);
			}
			else if (bPictures)
			{
				float MinU = 256.0f, MinV = 256.0f, MaxU = 0.0f, MaxV = 0.0f;
				for (int Corner = 0; Corner < Count; ++Corner)
				{
					MinU = std::min(MinU, Corners[static_cast<std::size_t>(Corner)].U);
					MinV = std::min(MinV, Corners[static_cast<std::size_t>(Corner)].V);
					MaxU = std::max(MaxU, Corners[static_cast<std::size_t>(Corner)].U);
					MaxV = std::max(MaxV, Corners[static_cast<std::size_t>(Corner)].V);
				}
				Look.Clamp = {MinU / 256.0f, MinV / 256.0f, MaxU / 256.0f, MaxV / 256.0f};
				++SceneryHd;
				SceneryHdMixed += SceneryRegionMixed(Vram, Page, Clut, MinU, MinV, MaxU, MaxV) ? 1 : 0;
				if (Blend != EBlend::Opaque)
				{
					// The page's picture spans its 256 x 256 texel coordinates (uv / 256).
					NoteSemiPicture(Key, Vram, Page, Clut, 0, 0, 256, 256);
					NoteRim(Key, static_cast<int>(std::floor(MinU)), static_cast<int>(std::floor(MinV)),
						std::max(static_cast<int>(std::floor(MinU)), static_cast<int>(std::ceil(MaxU)) - 1),
						std::max(static_cast<int>(std::floor(MinV)), static_cast<int>(std::ceil(MaxV)) - 1));
				}
				for (FCorner& Corner : Corners)
				{
					Corner.U /= 256.0f;
					Corner.V /= 256.0f;
				}
				++HdUpload;
				PushPrimitive(Into.Get(Blend, Key), Corners, Count, Look);
			}
			else if (bTextured)
			{
				++FromVram;
				++SceneryVram;
				PushPrimitive(Into.Get(Blend, {}), Corners, Count, Look);
			}
			else
			{
				PushPrimitive(Into.Get(Blend, {}), Corners, Count, Look);
			}
		}

		/**
		 * A quad facing the screen whose corners a GTE matrix puts in view space: a sprite's piece or a particle. Weltall gives
		 * a sprite's piece its whole cell, w x h, with texels to one past the last; the game's own UVs end at the last texel,
		 * w - 1 and h - 1, stretched over the cell, and the pack's pictures are made for that (the user's model of a frame,
		 * xeno_sprites/tools/eyepatch_fix/patch_game.py game_part, checked against the game). Nearer gives the piece's place
		 * in depth: cells overlap, and the PS1 draws a sprite's first pieces over its later ones (the model's layouts list
		 * them the other way round and paint the last on top).
		 */
		void PushViewQuad(FCollector& Into, const FVram& Vram, const FGteMatrix& Matrix, const std::array<FGteVector, 4>& Corners,
			const std::array<std::array<int16, 2>, 4>& Texels, uint16 PageAttribute, uint16 ClutAttribute, bool bPortRows, uint32 Color, bool bRaw,
			bool bSemi, bool bSprite, bool bPackPicture = true, float Nearer = 1.0f)
		{
			std::array<std::array<float, 3>, 4> Places{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				Places[Corner] = ToGodot(ViewPoint(Matrix, Corners[Corner]));
				for (float& Axis : Places[Corner])
				{
					Axis *= Nearer;
				}
			}
			PushViewQuadAt(Into, Vram, Places, Texels, PageAttribute, ClutAttribute, bPortRows, Color, bRaw, bSemi, bSprite, bPackPicture);
		}

		/** PushViewQuad with its corners already placed (Godot's view space, or the battle's 2D layer's pixels). */
		void PushViewQuadAt(FCollector& Into, const FVram& Vram, const std::array<std::array<float, 3>, 4>& Places,
			std::array<std::array<int16, 2>, 4> Texels, uint16 PageAttribute, uint16 ClutAttribute, bool bPortRows, uint32 Color, bool bRaw,
			bool bSemi, bool bSprite, bool bPackPicture)
		{
			if (bSprite)
			{
				// Corners 0 and 2 hold U0, 1 and 3 U1; 0 and 1 V0, 2 and 3 V1.
				const int Columns = Texels[1][0] - Texels[0][0], Rows = Texels[2][1] - Texels[0][1];
				const int16 LastU = std::max(Texels[0][0], Texels[1][0]), LastV = std::max(Texels[0][1], Texels[2][1]);
				for (auto& Texel : Texels)
				{
					Texel[0] = static_cast<int16>(Texel[0] == LastU && Columns != 0 ? Texel[0] - 1 : Texel[0]);
					Texel[1] = static_cast<int16>(Texel[1] == LastV && Rows != 0 ? Texel[1] - 1 : Texel[1]);
				}
			}
			const FTexturePage Page = bPortRows ? FTexturePage::FromPortAttribute(PageAttribute) : FTexturePage::FromAttribute(PageAttribute);
			const FClutPosition Clut = bPortRows ? FClutPosition::FromPortAttribute(ClutAttribute) : FClutPosition::FromAttribute(ClutAttribute);
			FLook Look;
			SetPage(Look, Page, Clut);
			Look.Flags = (bRaw ? FlagRaw : 0.0f) + (bSemi ? FlagSemi : 0.0f);
			Look.Order = CurrentOrder;
			int16 MinU = 255, MinV = 255, MaxU = 0, MaxV = 0;
			for (const auto& Texel : Texels)
			{
				MinU = std::min(MinU, Texel[0]);
				MinV = std::min(MinV, Texel[1]);
				MaxU = std::max(MaxU, Texel[0]);
				MaxV = std::max(MaxV, Texel[1]);
			}
			// A sprite's texels end at the last (above); a particle's far edges lie one past its last texel.
			const int16 Past = bSprite ? 0 : 1;
			Look.Clamp = {static_cast<float>(MinU), static_cast<float>(MinV), static_cast<float>(std::max<int16>(MinU, MaxU - Past)),
				static_cast<float>(std::max<int16>(MinV, MaxV - Past))};
			std::array<FCorner, 4> Quad{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				Quad[Corner].Pos = Places[Corner];
				Quad[Corner].Color = {static_cast<uint8_t>(Color), static_cast<uint8_t>(Color >> 8), static_cast<uint8_t>(Color >> 16)};
				Quad[Corner].U = Texels[Corner][0];
				Quad[Corner].V = Texels[Corner][1];
			}
			// Lit as the ground under it would be: half toward the camera, half up the screen.
			static const std::array<float, 3> Facing{0.0f, 0.5f, 0.866f};
			// A battle is drawn as the game draws it: its shadows are always the game's own.
			if (!bPackPicture && Options.bSoftShadows && !bBattleDrawing)
			{
				// Only where the game's own shadow shows: an actor kept invisible has one of transparent texels.
				const int MidU = (MinU + MaxU) / 2, MidV = (MinV + MaxV) / 2;
				const int Per = TexelsPerUnit(Page.Depth);
				const uint16 Word = Vram.TexelAt(Page.X + MidU / Per, Page.Y + MidV);
				const uint16 Texel = Page.Depth == ETextureDepth::Indexed4 ? Vram.TexelAt(Clut.X + (Word >> ((MidU & 3) * 4) & 15), Clut.Y)
					: Page.Depth == ETextureDepth::Indexed8 ? Vram.TexelAt(Clut.X + (Word >> ((MidU & 1) * 8) & 255), Clut.Y)
					: Word;
				if (Texel == 0)
				{
					return;
				}
				// A soft ellipse across the quad the game lays on the floor.
				Look.Depth = 5.0f;
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					Quad[Corner].U = (Corner & 1) != 0 ? 1.0f : 0.0f;
					Quad[Corner].V = (Corner & 2) != 0 ? 1.0f : 0.0f;
					// A hair toward the camera, over the floor it lies on (the PS1 draws it after the floor; here depth decides).
					for (float& Axis : Quad[Corner].Pos)
					{
						Axis *= 0.997f;
					}
				}
				PushPrimitive(Into.Get(EBlend::Average, {}), Quad, 4, Look, &Facing);
				return;
			}
			if (!bPackPicture)
			{
				++FromVram;
				PushPrimitive(Into.Get(bSemi ? BlendOf(Page.Blend) : EBlend::Opaque, {}), Quad, 4, Look, &Facing);
				return;
			}
			// A sprite's texels end at the last one (above), a particle's one past it.
			PushTextured(Into, FrameHits, Vram, bSemi ? BlendOf(Page.Blend) : EBlend::Opaque, Quad, 4, Look, Page, Clut, !bSprite, bSprite, &Facing,
				bSprite ? ETally::Sprite : ETally::None);
		}

		/**
		 * The 2D layer's primitives (the field's Screen, the battle's HUD, a menu's, the notice's, a card's) pushed in the
		 * list's order: those from First to End, without those of SkippedKey (0: none skipped).
		 */
		void PushDrawList(FCollector& Into, const FVram& Vram, const FDrawList& List, std::size_t First = 0, std::size_t End = SIZE_MAX,
			uint32 SkippedKey = 0, bool bTallied = true)
		{
			End = std::min(End, List.Primitives.size());
			for (std::size_t Index = First; Index < End; ++Index)
			{
				const FDrawPrimitive& Primitive = List.Primitives[Index];
				if (SkippedKey != 0 && Primitive.BlendKey == SkippedKey)
				{
					continue;
				}
				MixScreen(Primitive);
				FLook Look;
				EBlend Blend = EBlend::Opaque;
				const bool bSemi = Primitive.Blend != EDrawBlend::Opaque;
				if (Primitive.Texture)
				{
					SetPage(Look, Primitive.Texture->Page, Primitive.Texture->Clut);
					Blend = bSemi ? BlendOf(Primitive.Texture->Page.Blend) : EBlend::Opaque;
				}
				else if (bSemi)
				{
					Blend = BlendOf(Primitive.UntexturedBlend);
				}
				Look.Flags = (Primitive.bModulate ? 0.0f : FlagRaw) + (bSemi ? FlagSemi : 0.0f)
					+ (Primitive.Blend == EDrawBlend::SemiTransparentAll ? FlagSemiAll : 0.0f);
				Look.Spans = Primitive.bSpansDisplay || bListSpans ? 1.0f : 0.0f;
				// A list of a screen with other lines than the layer's (the world map's 216 under a menu's 224, a card's 224 over
				// the world map's 216): each screen is fitted to the display's height, centred, so its pixels scale about the
				// middle column (ListScale = the layer's lines over the list's). A list whose screen counts more columns across
				// the same width (the arena's winner screen) has them scaled first (ListColumnScale).
				const auto ScaledX = [this](float X) { return ListScale == 1.0f && ListColumnScale == 1.0f ? X : 160.0f + (X * ListColumnScale - 160.0f) * ListScale; };
				const auto ScaledY = [this](float Y) { return Y * ListScale; };
				// The GPU's drawing area (a menu's list window): only the pixels inside it are drawn.
				if (!(Primitive.Clip == WholeDrawingArea))
				{
					const FScreenRect& Clip = Primitive.Clip;
					Look.Area = {ScaledX(static_cast<float>(Clip.X)), ScaledY(static_cast<float>(Clip.Y)), ScaledX(static_cast<float>(Clip.X + Clip.Width)),
						ScaledY(static_cast<float>(Clip.Y + Clip.Height))};
				}
				if (Primitive.Texels)
				{
					Look.Clamp = {static_cast<float>(Primitive.Texels->FirstU), static_cast<float>(Primitive.Texels->FirstV),
						static_cast<float>(Primitive.Texels->LastU), static_cast<float>(Primitive.Texels->LastV)};
				}
				// A primitive spread over the whole display has its corners at the display's corners whatever their places in
				// the list, its texels across it as they lie (DrawList.h, bSpansDisplay; Weltall's DrawListRendering.cpp): here
				// the layer's screen's corners, which the 2D layer spreads across the whole window (main.gd, spans).
				const FScreenSize Layer = ScreenSizeOf(ScreenNow());
				std::array<FCorner, 4> Corners{};
				for (std::size_t Corner = 0; Corner < Primitive.CornerCount; ++Corner)
				{
					const FDrawVertex& Vertex = Primitive.Corners[Corner];
					const FDrawColor& Color = Primitive.bGouraud ? Vertex.Color : Primitive.Corners[0].Color;
					Corners[Corner].Pos = {ScaledX(Vertex.X), ScaledY(Vertex.Y), 0.0f};
					if (Primitive.bSpansDisplay && Primitive.CornerCount == 4)
					{
						Corners[Corner].Pos = {(Corner & 1) != 0 ? static_cast<float>(Layer.Width) : 0.0f, (Corner & 2) != 0 ? static_cast<float>(Layer.Height) : 0.0f, 0.0f};
					}
					else if (bListSpans)
					{
						Corners[Corner].Pos[0] = Vertex.X;
					}
					Corners[Corner].Color = {Color.R, Color.G, Color.B};
					Corners[Corner].U = Vertex.U;
					Corners[Corner].V = Vertex.V;
				}
				// A texture in the port's second VRAM state is drawn from VRAM (not passed on yet): textured, never from the pack.
				// The sweep's tallies are of the game's own 2D layer (not of a card the display draws over it).
				ScreenTextured += Primitive.Texture && bTallied ? 1 : 0;
				Into.Area = Look.Area;
				DumpPath = Primitive.Texture ? "vram (second state)" : "untextured";
				if (Report != nullptr)
				{
					Report->Who = "2D primitive " + std::to_string(Index);
				}
				if (Primitive.Texture && Primitive.Texture->Vram == 0)
				{
					PushTextured(Into, FrameHits, Vram, Blend, Corners, Primitive.CornerCount, Look, Primitive.Texture->Page, Primitive.Texture->Clut,
						Primitive.Texels.has_value(), false, nullptr, bTallied ? ETally::Screen : ETally::None, true);
				}
				else
				{
					PushPrimitive(Into.Get(Blend, {}), Corners, Primitive.CornerCount, Look);
				}
				if (Dumping2D())
				{
					Dump("2d %zu key %08x blend %d semi %d modulate %d", Index, Primitive.BlendKey, static_cast<int>(Blend),
						static_cast<int>(Primitive.Blend), Primitive.bModulate ? 1 : 0);
					if (Primitive.Texture)
					{
						Dump(" page %d,%d depth %d pageblend %d clut %d,%d", Primitive.Texture->Page.X, Primitive.Texture->Page.Y,
							static_cast<int>(Primitive.Texture->Page.Depth), static_cast<int>(Primitive.Texture->Page.Blend), Primitive.Texture->Clut.X,
							Primitive.Texture->Clut.Y);
					}
					if (Primitive.Texels)
					{
						Dump(" texels %d,%d-%d,%d", Primitive.Texels->FirstU, Primitive.Texels->FirstV, Primitive.Texels->LastU,
							Primitive.Texels->LastV);
					}
					if (!(Primitive.Clip == WholeDrawingArea))
					{
						Dump(" clip %d,%d %dx%d", Primitive.Clip.X, Primitive.Clip.Y, Primitive.Clip.Width, Primitive.Clip.Height);
					}
					Dump(" colour %d,%d,%d", Primitive.Corners[0].Color.R, Primitive.Corners[0].Color.G, Primitive.Corners[0].Color.B);
					Dump(" corners");
					for (std::size_t Corner = 0; Corner < Primitive.CornerCount; ++Corner)
					{
						Dump(" (%g,%g uv %g,%g)", Primitive.Corners[Corner].X, Primitive.Corners[Corner].Y, Primitive.Corners[Corner].U,
							Primitive.Corners[Corner].V);
					}
					Dump(" -> %s\n", DumpPath.c_str());
				}
			}
			Into.Area = {-1.0f, -1.0f, -1.0f, -1.0f};
		}

		// ---- The scene's generation: the "page:" textures and the scenery caches belong to one map, or one battle ----

		/** Counts the scenes drawn since the session opened (Info's MapLoads): a new map, a new program, a battle whose setup loads finished. */
		int SceneGeneration = 0;
		int64 SceneKey = -1;

		void FollowScene()
		{
			int64 Key = -1;
			if (Loop)
			{
				Key = static_cast<int64>(Loop->ProgramRuns()) << 32;
				if (const FFieldProgram* Running = Field())
				{
					Key |= static_cast<uint32>(Running->Runtime().MapLoads());
				}
				else if (const FBattleGameProgram* Fight = Battle())
				{
					// The stage's textures are all in VRAM once the setup's loads are done.
					Key |= Fight->Presentation().Show.HasStarted() ? 1u : 0u;
				}
				else if (const FWorldMapProgram* Map = WorldMap())
				{
					// The scene's textures are all in VRAM once its start has drawn the first frame.
					Key |= Map->LatestFrame() != nullptr ? 1u : 0u;
				}
				else if (const FBattlingGameProgram* Arena = Battling())
				{
					// The arena's pictures are uploaded as it starts; the two gears' textures as their bout is chosen and
					// loaded (at the start for the field's bouts, after the menus' choice for theirs): a new pair is a new scene.
					Key |= 1u << 16 | static_cast<uint32>(Arena->Gears()[0]) << 8 | Arena->Gears()[1];
				}
			}
			if (Key != SceneKey)
			{
				SceneKey = Key;
				++SceneGeneration;
				ForgetScenery();
				// The pages are the new scene's: the display builds them again.
				ForgetReadyPages();
			}
		}

		// ---- The Battle program's frame. Adapted from Weltall's own renderer (MIT): Source/Weltall/Private/Rendering/
		// BattleFrameDraw.cpp (the links of the frame's order), BattleObjectsDraw.cpp (the stage's and the 3D objects'),
		// Screens/BattleView.cpp (the HUD through FMenuDrawBuilder). Drawn unlit, in the frame's drawing order: each
		// primitive of the scene gets its place in the order (C1's w), which the battle's shader writes as its depth, so the
		// later one covers the earlier as on the PS1 (the reference renderer's painter's order). What the GPU draws over the
		// fade or the HUD goes on the 2D layer in the order's sequence with them. ----

		bool bBattleDrawing = false;
		/** The place in the drawing order the primitives pushed now take (0 on the field and on the 2D layer). */
		float CurrentOrder = 0.0f;
		int OrderCount = 0;
		/** The links go onto the 2D layer (screen pixels of 320 x 224) rather than into the scene (Godot's view space). */
		bool bBattleToScreen = false;
		float BattleDistance = 512.0f, BattleAcross = 0.0f, BattleLower = 0.0f;
		/** The display's columns over the frame's (1 but on the arena's winner screen, whose 640 columns span the 320's width). */
		float BattleColumnScale = 1.0f;
		FMenuDrawBuilder HudBuilder;
		FMenuFrame HudFrame;
		FDrawList HudList;
		std::vector<FFieldBackdropQuad> BackdropQuads;
		/** Nearer than this (view units) a corner is behind the eye or at it: its primitive is not drawn (the GTE's own limit). */
		static constexpr float NearestDepth = 1.0f;

		const FBattleGameProgram* Battle() const { return Loop ? Loop->Battle() : nullptr; }

		/** The battle's frame once its show has begun (before that, the transition: nothing of the battle is drawn yet). */
		const FBattleShowFrame* BattleFrame() const
		{
			const FBattleGameProgram* Fight = Battle();
			if (Fight == nullptr || !Fight->Presentation().HasBegun())
			{
				return nullptr;
			}
			const FBattleShowFrame& Frame = Fight->Presentation().Show.Frame();
			return Frame.Vram != nullptr ? &Frame : nullptr;
		}

		/** VRAM of what is drawn now: the field's, or the battle frame's. */
		const FVram* SceneVram() const
		{
			if (const FFieldProgram* Running = Field())
			{
				return &Running->Drawing().Vram();
			}
			if (const FWorldMapProgram* Map = WorldMap())
			{
				return &Map->Drawing().Vram();
			}
			if (const FBattlingGameProgram* Arena = Battling())
			{
				// The arena's own: its pictures, both gears' textures, the fire, the typed lines (FBattlingGameProgram::Vram).
				return &Arena->Vram();
			}
			const FBattleShowFrame* Frame = BattleFrame();
			return Frame != nullptr ? Frame->Vram : nullptr;
		}

		/** Where the GPU draws the first layer (the fade or the HUD): the scene's links come before it. */
		static std::size_t FirstLayer(const FBattleShowFrame& Frame)
		{
			for (std::size_t Index = 0; Index < Frame.Order.size(); ++Index)
			{
				if (Frame.Order[Index].Kind == EBattleShowLink::Fade || Frame.Order[Index].Kind == EBattleShowLink::Hud)
				{
					return Index;
				}
			}
			return Frame.Order.size();
		}

		void BeginBattleDrawing(const FBattleShowFrame& Frame, bool bToScreen)
		{
			bBattleDrawing = true;
			bBattleToScreen = bToScreen;
			BattleWhole = BattleClipped = BattleBehind = 0;
			OrderCount = 0;
			CurrentOrder = 0.0f;
			BattleDistance = static_cast<float>(std::max<int32>(Frame.ProjectionDistance, 1));
			// The camera projects about the screen's middle; the battle's centre lies elsewhere (below it): each point moves
			// across and down in proportion to its depth (BattleFrameDraw.cpp, BuildBattleDraw).
			BattleColumnScale = 1.0f;
			BattleAcross = (static_cast<float>(Frame.CentreX) - 160.0f) / BattleDistance;
			BattleLower = (static_cast<float>(Frame.CentreY) - 112.0f) / BattleDistance;
		}

		void EndBattleDrawing()
		{
			(bBattleToScreen ? ScreenBehind : WorldBehind) = {BattleWhole, BattleClipped, BattleBehind};
			bBattleDrawing = false;
			bBattleToScreen = false;
			CurrentOrder = 0.0f;
		}

		/** A point of the frame's view space where it is drawn: Godot's view space, or the 2D layer's pixels. */
		std::array<float, 3> BattlePlace(const std::array<float, 3>& View) const
		{
			const float X = View[0] * BattleColumnScale + BattleAcross * View[2], Y = View[1] + BattleLower * View[2];
			if (bBattleToScreen)
			{
				return {160.0f + X * BattleDistance / View[2], 112.0f + Y * BattleDistance / View[2], 0.0f};
			}
			return ToGodot({X, Y, View[2]});
		}

		/** The next place in the drawing order: later ones cover earlier ones (from 0.02 up, a step each, at most 0.98). */
		void NextOrder()
		{
			CurrentOrder = bBattleToScreen ? 0.0f : std::min(0.98f, 0.02f + 1e-5f * static_cast<float>(++OrderCount));
		}

		/**
		 * Whether a polygon is drawn: in the scene, unless every corner is behind the eye (the GPU clips the rest at the
		 * eye's plane); on the 2D layer, which has no clipping, only with every corner in front of it.
		 */
		bool InFront(const std::array<std::array<float, 3>, 4>& View, int Count)
		{
			int Behind = 0;
			for (int Corner = 0; Corner < Count; ++Corner)
			{
				Behind += View[static_cast<std::size_t>(Corner)][2] < NearestDepth ? 1 : 0;
			}
			const bool bDrawn = bBattleToScreen ? Behind == 0 : Behind < Count;
			++(bDrawn ? (Behind > 0 ? BattleClipped : BattleWhole) : BattleBehind);
			return bDrawn;
		}
		/** The battle's polygons since BeginBattleDrawing: wholly in front of the eye, partly (clipped by the GPU), not drawn. */
		int BattleWhole = 0, BattleClipped = 0, BattleBehind = 0;
		/** The same for the last BuildWorld and the last BuildScreen. */
		std::array<int, 3> WorldBehind{}, ScreenBehind{};

		static std::array<uint8_t, 3> Rgb(uint32 Color)
		{
			return {static_cast<uint8_t>(Color), static_cast<uint8_t>(Color >> 8), static_cast<uint8_t>(Color >> 16)};
		}

		/** An untextured polygon (flat or a colour a corner), semi-transparent in Mode or opaque. */
		void PushBattleFlat(FCollector& Into, const std::array<std::array<float, 3>, 4>& View, int Count, const std::array<uint32, 4>& Colors, bool bSemi,
			EBlendMode Mode)
		{
			if (!InFront(View, Count))
			{
				return;
			}
			NextOrder();
			FLook Look;
			Look.Flags = bSemi ? FlagSemi : 0.0f;
			Look.Order = CurrentOrder;
			std::array<FCorner, 4> Corners{};
			for (int Corner = 0; Corner < Count; ++Corner)
			{
				const std::size_t At = static_cast<std::size_t>(Corner);
				Corners[At].Pos = BattlePlace(View[At]);
				Corners[At].Color = Rgb(Colors[At]);
			}
			PushPrimitive(Into.Get(bSemi ? BlendOf(Mode) : EBlend::Opaque, {}), Corners, Count, Look);
			if (Dumping2D())
			{
				// Untextured: where on the original's screen (320 x 224) each corner lies, its colour, its place in the order.
				Dump("flat %s semi %d mode %d order %d colour %06x corners", bBattleToScreen ? "screen" : "scene", bSemi ? 1 : 0, static_cast<int>(Mode), OrderCount,
					Colors[0]);
				for (int Corner = 0; Corner < Count; ++Corner)
				{
					Dump(" (%.1f,%.1f z %.0f)", BattleScreenX(View[static_cast<std::size_t>(Corner)]), BattleScreenY(View[static_cast<std::size_t>(Corner)]),
						View[static_cast<std::size_t>(Corner)][2]);
				}
				Dump("\n");
			}
		}

		/** Where a point of the battle's view lies on the original's screen (320 x 224): for the dumps. */
		float BattleScreenX(const std::array<float, 3>& View) const
		{
			return 160.0f + (View[0] * BattleColumnScale + BattleAcross * View[2]) * BattleDistance / View[2];
		}
		float BattleScreenY(const std::array<float, 3>& View) const
		{
			return 112.0f + (View[1] + BattleLower * View[2]) * BattleDistance / View[2];
		}

		/**
		 * A textured polygon through the pack's lookup (PushTextured): its texels end at the last one (bOnePast false; a
		 * region one texel narrower is tried too) or one before the far edge (bOnePast). Pages in the port's rows from VRAM.
		 */
		void PushBattleTextured(FCollector& Into, const FVram& Vram, const std::array<std::array<float, 3>, 4>& View, int Count,
			const std::array<std::array<float, 2>, 4>& Texels, const std::array<uint32, 4>& Colors, const FTexturePage& Page, const FClutPosition& Clut,
			bool bRaw, bool bSemi, bool bOnePast)
		{
			if (!InFront(View, Count))
			{
				return;
			}
			NextOrder();
			FLook Look;
			SetPage(Look, Page, Clut);
			Look.Flags = (bRaw ? FlagRaw : 0.0f) + (bSemi ? FlagSemi : 0.0f);
			Look.Order = CurrentOrder;
			float MinU = 1e9f, MinV = 1e9f, MaxU = -1e9f, MaxV = -1e9f;
			std::array<FCorner, 4> Corners{};
			for (int Corner = 0; Corner < Count; ++Corner)
			{
				const std::size_t At = static_cast<std::size_t>(Corner);
				Corners[At].Pos = BattlePlace(View[At]);
				Corners[At].Color = Rgb(Colors[At]);
				Corners[At].U = Texels[At][0];
				Corners[At].V = Texels[At][1];
				MinU = std::min(MinU, Texels[At][0]);
				MinV = std::min(MinV, Texels[At][1]);
				MaxU = std::max(MaxU, Texels[At][0]);
				MaxV = std::max(MaxV, Texels[At][1]);
			}
			const float Past = bOnePast ? 1.0f : 0.0f;
			Look.Clamp = {MinU, MinV, std::max(MinU, MaxU - Past), std::max(MinV, MaxV - Past)};
			const EBlend Blend = bSemi ? BlendOf(Page.Blend) : EBlend::Opaque;
			if (Page.Y >= FVram::Height)
			{
				++FromVram;
				PushPrimitive(Into.Get(Blend, {}), Corners, Count, Look);
				return;
			}
			PushTextured(Into, FrameHits, Vram, Blend, Corners, Count, Look, Page, Clut, bOnePast, false, nullptr, ETally::None, !bOnePast);
		}

		/** A quad the GTE projects: a sprite's piece (with the pack's lookup), a number's glyph, or a sprite's shadow (BattleFrameDraw.cpp AddQuad). */
		void AddBattleQuad(FCollector& Into, const FBattleShowFrame& Frame, const FVram& Vram, const FBattleShowQuad& Entry)
		{
			const FSpriteQuad& Quad = Entry.Quad;
			const bool bShadow = Entry.Drawer < Frame.Drawers.size() && Frame.Drawers[Entry.Drawer].Kind == EBattleShowDrawer::Shadow;
			std::array<std::array<float, 3>, 4> View{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				View[Corner] = Quad.ViewCorner(Corner);
			}
			if (!InFront(View, 4))
			{
				return;
			}
			if (bShadow)
			{
				// Once projected, the GPU's first two corners of a shadow take their average height on the screen, and the last two theirs.
				for (const std::array<std::size_t, 2>& Edge : {std::array<std::size_t, 2>{0, 1}, std::array<std::size_t, 2>{2, 3}})
				{
					std::array<float, 3>& A = View[Edge[0]];
					std::array<float, 3>& B = View[Edge[1]];
					const float Screen = (A[1] * BattleDistance / A[2] + B[1] * BattleDistance / B[2]) / 2.0f;
					A[1] = Screen * A[2] / BattleDistance;
					B[1] = Screen * B[2] / BattleDistance;
				}
			}
			NextOrder();
			std::array<std::array<float, 3>, 4> Places{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				Places[Corner] = BattlePlace(View[Corner]);
			}
			const std::array<std::array<int16, 2>, 4> Texels{{{Quad.U0, Quad.V0}, {Quad.U1, Quad.V0}, {Quad.U0, Quad.V1}, {Quad.U1, Quad.V1}}};
			DumpPath = "from VRAM (shadow)";
			// Only a sprite's part ends its texels at its last one (the w - 1 rule of PushViewQuad): the kernel's packet of a
			// part does. The HUD sheet's glyphs (the damage numbers, the total and its caption, FBattleShow::AddGlyphs) map
			// their texels edge to edge as their packets hold them, the last texel one before the far edge (Weltall's
			// BattleFrameDraw.cpp AddQuad gives every quad that). A quad that is no part's has no cell (FSpriteQuad::CellV0/V1 0).
			const bool bPart = WithoutTask8() || Quad.CellV0 != 0 || Quad.CellV1 != 0;
			BattleGlyphs += !bPart && !bShadow ? 1 : 0;
			if (Report != nullptr)
			{
				Report->Who = "battle quad, drawer " + std::to_string(Entry.Drawer) + " of kind "
					+ std::to_string(Entry.Drawer < Frame.Drawers.size() ? static_cast<int>(Frame.Drawers[Entry.Drawer].Kind) : -1) + (bPart ? "" : " (a glyph)");
			}
			// A sprite's parts may lie in VRAM's port rows (Id's battle sprite).
			PushViewQuadAt(Into, Vram, Places, Texels, Quad.TexturePage, Quad.Clut, true, Quad.ColorCode & 0xFFFFFF, (Quad.ColorCode >> 24 & 1) != 0,
				(Quad.ColorCode >> 25 & 1) != 0, !bShadow && bPart, !bShadow);
			if (Dumping2D())
			{
				const FTexturePage Page = FTexturePage::FromPortAttribute(Quad.TexturePage);
				const FClutPosition Clut = FClutPosition::FromPortAttribute(Quad.Clut);
				Dump("quad %s drawer %d kind %d code %08x page %d,%d depth %d pageblend %d clut %d,%d uv %d,%d-%d,%d cell v %d-%d corners",
					bBattleToScreen ? "screen" : "scene", Entry.Drawer, Entry.Drawer < Frame.Drawers.size() ? static_cast<int>(Frame.Drawers[Entry.Drawer].Kind) : -1,
					Quad.ColorCode, Page.X, Page.Y, static_cast<int>(Page.Depth), static_cast<int>(Page.Blend), Clut.X, Clut.Y, Quad.U0, Quad.V0, Quad.U1, Quad.V1,
					Quad.CellV0, Quad.CellV1);
				for (const auto& At : Places)
				{
					Dump(" (%g,%g,%g)", At[0], At[1], At[2]);
				}
				Dump(" -> %s\n", DumpPath.c_str());
			}
		}

		/** A target marker's triangle, a colour a corner (AddTriangle). */
		void AddBattleTriangle(FCollector& Into, const FBattleShowTriangle& Triangle)
		{
			std::array<std::array<float, 3>, 4> View{};
			std::array<uint32, 4> Colors{};
			for (std::size_t Corner = 0; Corner < 3; ++Corner)
			{
				View[Corner] = ViewPoint(Triangle.Matrix, Triangle.Corners[Corner]);
				Colors[Corner] = Triangle.ColorCodes[Corner] & 0xFFFFFF;
			}
			PushBattleFlat(Into, View, 3, Colors, (Triangle.ColorCodes[0] >> 24 & 2) != 0, EBlendMode::Average);
		}

		/** A spawned sprite's dot or square: flat on the screen about its place, at its place's depth (AddTile). */
		void AddBattleTile(FCollector& Into, const FBattleShowFrame& Frame, const FBattleShowTile& Tile)
		{
			const std::array<float, 3> Centre = ViewPoint(Frame.View, Tile.Place);
			if (Centre[2] < NearestDepth)
			{
				return;
			}
			const float Pixel = Centre[2] / BattleDistance;
			float Side = Pixel;
			if (!Tile.bDot)
			{
				const FGteVector Along{static_cast<int16>(Tile.Place[0] + Tile.Size), Tile.Place[1], Tile.Place[2]};
				const std::array<float, 3> Edge = ViewPoint(Frame.View, Along);
				if (Edge[2] > 0.0f)
				{
					Side = std::max(std::abs(Edge[0] / Edge[2] - Centre[0] / Centre[2]) * BattleDistance, 1.0f) * Pixel;
				}
			}
			const float Left = Centre[0] + Pixel / 2.0f - Side / 2.0f, Top = Centre[1] + Pixel / 2.0f - Side / 2.0f;
			std::array<std::array<float, 3>, 4> View{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				View[Corner] = {Left + ((Corner & 1) != 0 ? Side : 0.0f), Top + ((Corner & 2) != 0 ? Side : 0.0f), Centre[2]};
			}
			const uint32 Color = Tile.ColorCode & 0xFFFFFF;
			PushBattleFlat(Into, View, 4, {Color, Color, Color, Color}, (Tile.ColorCode >> 25 & 1) != 0, static_cast<EBlendMode>(Tile.Blend & 3));
		}

		/** A spawned sprite's line, a pixel of the original's screen wide, each end at its depth (AddLine). */
		void AddBattleLine(FCollector& Into, const FBattleShowLine& Line)
		{
			const std::array<float, 3> From = ViewPoint(Line.Matrix, Line.Ends[0]), To = ViewPoint(Line.Matrix, Line.Ends[1]);
			if (From[2] < NearestDepth || To[2] < NearestDepth)
			{
				return;
			}
			const float D = BattleDistance;
			const float StartX = From[0] / From[2] * D + 0.5f, StartY = From[1] / From[2] * D + 0.5f;
			const float EndX = To[0] / To[2] * D + 0.5f, EndY = To[1] / To[2] * D + 0.5f;
			float AlongX = EndX - StartX, AlongY = EndY - StartY;
			const float Length = std::sqrt(AlongX * AlongX + AlongY * AlongY);
			if (Length < 1e-6f)
			{
				AlongX = 1.0f;
				AlongY = 0.0f;
			}
			else
			{
				AlongX /= Length;
				AlongY /= Length;
			}
			const float SideX = -AlongY * 0.5f, SideY = AlongX * 0.5f;
			const std::array<std::array<float, 2>, 4> Screen{{{StartX - AlongX * 0.5f - SideX, StartY - AlongY * 0.5f - SideY},
				{StartX - AlongX * 0.5f + SideX, StartY - AlongY * 0.5f + SideY}, {EndX + AlongX * 0.5f - SideX, EndY + AlongY * 0.5f - SideY},
				{EndX + AlongX * 0.5f + SideX, EndY + AlongY * 0.5f + SideY}}};
			const std::array<float, 4> Depths{From[2], From[2], To[2], To[2]};
			std::array<std::array<float, 3>, 4> View{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				View[Corner] = {Screen[Corner][0] * Depths[Corner] / D, Screen[Corner][1] * Depths[Corner] / D, Depths[Corner]};
			}
			const uint32 Color = Line.ColorCode & 0xFFFFFF;
			PushBattleFlat(Into, View, 4, {Color, Color, Color, Color}, (Line.ColorCode >> 25 & 1) != 0,
				Line.Blend >= 0 ? static_cast<EBlendMode>(Line.Blend & 3) : EBlendMode::Average);
		}

		/** A quad placed on the screen (a span of a script's trail), each corner at its end's depth (AddScreenQuad). */
		void AddBattleScreenQuad(FCollector& Into, const FBattleShowFrame& Frame, const FVram& Vram, const FBattleShowScreenQuad& Quad)
		{
			if (Quad.Depths[0] <= 0 || Quad.Depths[1] <= 0)
			{
				return;
			}
			std::array<std::array<float, 3>, 4> View{};
			std::array<std::array<float, 2>, 4> Texels{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				const float Depth = static_cast<float>(Quad.Depths[Corner >> 1]);
				View[Corner] = {static_cast<float>(Quad.Corners[Corner][0] - Frame.CentreX) * Depth / BattleDistance,
					static_cast<float>(Quad.Corners[Corner][1] - Frame.CentreY) * Depth / BattleDistance, Depth};
				Texels[Corner] = {static_cast<float>((Corner & 1) != 0 ? Quad.U1 : Quad.U0), static_cast<float>((Corner & 2) != 0 ? Quad.V1 : Quad.V0)};
			}
			const uint32 Color = Quad.ColorCode & 0xFFFFFF;
			PushBattleTextured(Into, Vram, View, 4, Texels, {Color, Color, Color, Color}, FTexturePage::FromPortAttribute(Quad.TexturePage),
				FClutPosition::FromPortAttribute(Quad.Clut), (Quad.ColorCode >> 24 & 1) != 0, (Quad.ColorCode >> 25 & 1) != 0, true);
		}

		/** A polygon of a model a sprite draws, about its model's own centre on the screen (AddModelPolygon). */
		void AddBattleModelPolygon(FCollector& Into, const FBattleShowFrame& Frame, const FVram& Vram, const FBattleShowModelPolygon& Polygon)
		{
			if (Polygon.Model >= Frame.Models.size())
			{
				return;
			}
			const FBattleShowModel& Model = Frame.Models[Polygon.Model];
			const float Across = static_cast<float>(Model.CentreX - Frame.CentreX) / BattleDistance;
			const float Lower = static_cast<float>(Model.CentreY - Frame.CentreY) / BattleDistance;
			const int Count = Polygon.CornerCount == 4 ? 4 : 3;
			std::array<std::array<float, 3>, 4> View{};
			std::array<std::array<float, 2>, 4> Texels{};
			std::array<uint32, 4> Colors{};
			for (std::size_t Corner = 0; Corner < static_cast<std::size_t>(Count); ++Corner)
			{
				const std::array<float, 3> Point = ViewPoint(Model.Matrix, Polygon.Corners[Corner]);
				View[Corner] = {Point[0] + Across * Point[2], Point[1] + Lower * Point[2], Point[2]};
				Texels[Corner] = {static_cast<float>(Polygon.Uvs[Corner].U), static_cast<float>(Polygon.Uvs[Corner].V)};
				Colors[Corner] = Polygon.ColorCodes[Polygon.bGouraud ? Corner : 0] & 0xFFFFFF;
			}
			const bool bSemi = (Polygon.ColorCodes[0] >> 25 & 1) != 0;
			if (Polygon.bTextured)
			{
				PushBattleTextured(Into, Vram, View, Count, Texels, Colors, FTexturePage::FromAttribute(Polygon.TexturePage),
					FClutPosition::FromAttribute(Polygon.Clut), (Polygon.ColorCodes[0] >> 24 & 1) != 0, bSemi, false);
			}
			else
			{
				PushBattleFlat(Into, View, Count, Colors, bSemi, Polygon.Blend >= 0 ? static_cast<EBlendMode>(Polygon.Blend & 3) : EBlendMode::Average);
			}
		}

		/** A polygon of the stage's or a 3D object's (a gear's) part, a floor shadow, a cloth's triangle or a trail's quad (BattleObjectsDraw.cpp). */
		void AddBattleObject(FCollector& Into, const FBattleShowFrame& Frame, const FVram& Vram, const FBattleObjectLink& Link)
		{
			const FBattleObjectsFrame& Objects = *Frame.Objects;
			std::array<std::array<float, 3>, 4> View{};
			std::array<FMdlUv, 4> Uvs{};
			std::array<FMdlColor, 4> Colors{};
			int Count = 3;
			bool bGouraud = false;
			uint16 PageAttribute = 0, ClutAttribute = 0;
			bool bPortRows = false;
			uint8 Code = 0;
			bool bModel = false;
			switch (Link.Kind)
			{
			case EBattleObjectDraw::Polygon:
			{
				if (Link.Index >= Objects.Polygons.size())
				{
					return;
				}
				const FBattleDrawnPolygon& Drawn = Objects.Polygons[Link.Index];
				const FBattleDrawnPart& Part = Objects.Parts[Drawn.Part];
				const FMdlPrimitive& Primitive = Part.Part->Primitives[Drawn.Number];
				const FMdlPrimitiveTraits& Traits = Primitive.Traits();
				Count = Traits.Corners;
				for (std::size_t Corner = 0; Corner < Traits.Corners; ++Corner)
				{
					View[Corner] = ViewPoint(Part.Matrix, Part.Part->Vertices[Primitive.Vertices[Corner]]);
				}
				if (Primitive.Type == EMdlPrimitiveType::EnvironmentMappedTriangle)
				{
					std::copy(Drawn.Texels.begin(), Drawn.Texels.end(), Uvs.begin());
				}
				else
				{
					Uvs = Primitive.Uvs;
				}
				Colors = Drawn.Colors;
				bGouraud = Traits.bGouraud;
				if (!Traits.bTextured)
				{
					PageAttribute = 0xFFFF; // untextured
					if (Dumping2D())
					{
						Dump("untextured object slot %d bone %d primitive %d type %d gouraud %d relight %d corners %d colours %02x%02x%02x %02x%02x%02x\n", Part.Slot, Part.Bone,
							Drawn.Number, static_cast<int>(Primitive.Type), Traits.bGouraud ? 1 : 0, static_cast<int>(Part.Packets->Packets[Drawn.Number].Relight),
							Count, Drawn.Colors[0].R, Drawn.Colors[0].G, Drawn.Colors[0].B, Drawn.Colors[1].R, Drawn.Colors[1].G, Drawn.Colors[1].B);
					}
				}
				else
				{
					PageAttribute = Part.Packets->Textures[Drawn.Number].TexturePage;
					ClutAttribute = Part.Packets->Textures[Drawn.Number].Clut;
				}
				bPortRows = Part.bPortRows;
				Code = Part.Packets->Packets[Drawn.Number].Code;
				bModel = true;
				break;
			}
			case EBattleObjectDraw::Shadow:
			{
				if (Link.Index >= Objects.Shadows.size())
				{
					return;
				}
				const FBattleDrawnShadow& Shadow = Objects.Shadows[Link.Index];
				Count = 4;
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					View[Corner] = ViewPoint(Shadow.Matrix, Shadow.Corners[Corner]);
				}
				using namespace BattleObjectShadow;
				Uvs = {{{FirstTexel, FirstTexel}, {LastTexel, FirstTexel}, {FirstTexel, LastTexel}, {LastTexel, LastTexel}}};
				Colors[0] = Shadow.Colour;
				PageAttribute = TexturePage;
				ClutAttribute = Clut;
				Code = BattleObjectShadow::Code;
				break;
			}
			case EBattleObjectDraw::Cloth:
			{
				if (Link.Index >= Objects.Cloths.size())
				{
					return;
				}
				const FGearDrawnClothTriangle& Triangle = Objects.Cloths[Link.Index];
				const FAffine ClothView = FAffine::From(Objects.View);
				for (std::size_t Corner = 0; Corner < 3; ++Corner)
				{
					const FGteVector& Point = Triangle.Points[Corner];
					const std::array<float, 3> Turned =
						ClothView.Turn({static_cast<float>(Point[0]), static_cast<float>(Point[1]), static_cast<float>(Point[2])});
					View[Corner] = {Turned[0] + ClothView.T[0], Turned[1] + ClothView.T[1], Turned[2] + ClothView.T[2]};
					Uvs[Corner] = Triangle.Uvs[Corner];
					Colors[Corner] = Triangle.Colors[Corner];
				}
				bGouraud = true;
				PageAttribute = Triangle.TexturePage;
				ClutAttribute = Triangle.Clut;
				Code = GearClothCode;
				bModel = true;
				break;
			}
			case EBattleObjectDraw::Trail:
			{
				if (Link.Index >= Objects.Trails.size())
				{
					return;
				}
				const FBattleTrailQuad& Quad = Objects.Trails[Link.Index];
				Count = 4;
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					const FGteVector& At = Quad.Corners[Corner];
					View[Corner] = Quad.Kind == 0 ? std::array<float, 3>{static_cast<float>(At[0] - Frame.CentreX), static_cast<float>(At[1] - Frame.CentreY),
														static_cast<float>(Frame.ProjectionDistance)}
												  : ViewPoint(Objects.View, At);
				}
				using namespace BattleTrailQuad;
				Uvs = {{{0, Row}, {0, Row}, {LastTexel, Row}, {LastTexel, Row}}};
				Colors[0] = {Quad.Colour[0], Quad.Colour[1], Quad.Colour[2]};
				PageAttribute = TexturePage;
				ClutAttribute = Clut;
				Code = Quad.bSemiTransparent ? SemiTransparentCode : BattleTrailQuad::Code;
				break;
			}
			}
			if (!InFront(View, Count))
			{
				return;
			}
			std::array<uint32, 4> Packed{};
			std::array<std::array<float, 2>, 4> Texels{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				const FMdlColor& Color = Colors[bGouraud ? Corner : 0];
				Packed[Corner] = static_cast<uint32>(Color.R | Color.G << 8 | Color.B << 16);
				Texels[Corner] = {static_cast<float>(Uvs[Corner].U), static_cast<float>(Uvs[Corner].V)};
			}
			const bool bSemi = (Code & 2) != 0, bRaw = (Code & 1) != 0;
			if (PageAttribute == 0xFFFF)
			{
				PushBattleFlat(Into, View, Count, Packed, bSemi, EBlendMode::Average);
				return;
			}
			const FTexturePage Page = bPortRows ? FTexturePage::FromPortAttribute(PageAttribute) : FTexturePage::FromAttribute(PageAttribute);
			const FClutPosition Clut = bPortRows ? FClutPosition::FromPortAttribute(ClutAttribute) : FClutPosition::FromAttribute(ClutAttribute);
			if (!bModel)
			{
				PushBattleTextured(Into, Vram, View, Count, Texels, Packed, Page, Clut, bRaw, bSemi, false);
				return;
			}
			// The stage's and the gears' models as the field's scenery: from the page with the pack's pictures laid in.
			NextOrder();
			const std::string WhoBefore = Report != nullptr ? Report->Who : std::string();
			if (Report != nullptr)
			{
				// Where on the original's screen it lies (the report's "who").
				char Where[160];
				std::snprintf(Where, sizeof(Where), ", order %d, screen (%.0f,%.0f) (%.0f,%.0f) (%.0f,%.0f) (%.0f,%.0f)", OrderCount, BattleScreenX(View[0]), BattleScreenY(View[0]),
					BattleScreenX(View[1]), BattleScreenY(View[1]), BattleScreenX(View[2]), BattleScreenY(View[2]), BattleScreenX(View[Count > 3 ? 3 : 2]),
					BattleScreenY(View[Count > 3 ? 3 : 2]));
				Report->Who += Where;
			}
			FLook Look;
			SetPage(Look, Page, Clut);
			Look.Flags = (bRaw ? FlagRaw : 0.0f) + (bSemi ? FlagSemi : 0.0f);
			Look.Order = CurrentOrder;
			std::array<FCorner, 4> Corners{};
			for (std::size_t Corner = 0; Corner < static_cast<std::size_t>(Count); ++Corner)
			{
				Corners[Corner].Pos = BattlePlace(View[Corner]);
				Corners[Corner].Color = Rgb(Packed[Corner]);
				Corners[Corner].U = Texels[Corner][0];
				Corners[Corner].V = Texels[Corner][1];
			}
			PushScenery(Into, Vram, Corners, Count, Look, true, Page, Clut, bSemi ? BlendOf(Page.Blend) : EBlend::Opaque);
			if (Report != nullptr)
			{
				Report->Who = WhoBefore;
			}
		}

		/**
		 * A backdrop packet placed far behind where Screen puts it on the screen, raw textured in its window or its own
		 * texels, or a colour band (AddBackdropQuad).
		 */
		void AddBattleBackdropQuad(FCollector& Into, const FBattleShowFrame& Frame, const FVram& Vram, const FFieldBackdropQuad& Quad,
			const std::array<std::array<float, 2>, 4>& Screen, bool bSemi, const std::optional<std::array<int16, 4>>& Window, EBlendMode PageBlend)
		{
			constexpr float Depth = 65536.0f;
			const float Scale = Depth / BattleDistance;
			std::array<std::array<float, 3>, 4> View{};
			std::array<uint32, 4> Colors{};
			std::array<std::array<float, 2>, 4> Texels{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				View[Corner] = {(Screen[Corner][0] - static_cast<float>(Frame.CentreX)) * Scale, (Screen[Corner][1] - static_cast<float>(Frame.CentreY)) * Scale, Depth};
				const std::size_t Tint = Quad.Kind == FFieldBackdropQuad::EKind::Graded ? Corner : 0;
				Colors[Corner] = static_cast<uint32>(Quad.Colors[Tint][0] | Quad.Colors[Tint][1] << 8 | Quad.Colors[Tint][2] << 16);
				Texels[Corner] = {static_cast<float>(Quad.Texels[Corner][0]), static_cast<float>(Quad.Texels[Corner][1])};
			}
			if (Dumping2D())
			{
				Dump("backdrop kind %d semi %d page %04x clut %04x window %s colour %02x%02x%02x screen", static_cast<int>(Quad.Kind), bSemi ? 1 : 0, Quad.TexturePage,
					Quad.Clut, Window ? "yes" : "no", Quad.Colors[0][0], Quad.Colors[0][1], Quad.Colors[0][2]);
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					Dump(" (%.0f,%.0f uv %.0f,%.0f)", Screen[Corner][0], Screen[Corner][1], Texels[Corner][0], Texels[Corner][1]);
				}
				Dump("\n");
			}
			if (Quad.Kind != FFieldBackdropQuad::EKind::Textured)
			{
				PushBattleFlat(Into, View, 4, Colors, bSemi, PageBlend);
				return;
			}
			const FTexturePage Page = FTexturePage::FromAttribute(Quad.TexturePage);
			const FClutPosition Clut = FClutPosition::FromAttribute(Quad.Clut);
			if (!Window)
			{
				// Raw texels; the packet's texels run to the far column and row themselves.
				PushBattleTextured(Into, Vram, View, 4, Texels, Colors, Page, Clut, true, bSemi, false);
				return;
			}
			// Texels wrapping in a texture window (the floor dome's cells): from VRAM, the window in the shader.
			NextOrder();
			FLook Look;
			SetPage(Look, Page, Clut);
			Look.Flags = FlagRaw + (bSemi ? FlagSemi : 0.0f) + FlagWindow;
			Look.Order = CurrentOrder;
			const std::array<int16, 4>& Rectangle = *Window;
			Look.Clamp = {static_cast<float>(Rectangle[0]), static_cast<float>(Rectangle[1]), static_cast<float>(~(Rectangle[2] - 1) & 0xFF),
				static_cast<float>(~(Rectangle[3] - 1) & 0xFF)};
			std::array<FCorner, 4> Corners{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				Corners[Corner].Pos = BattlePlace(View[Corner]);
				Corners[Corner].Color = Rgb(Colors[Corner]);
				Corners[Corner].U = Texels[Corner][0];
				Corners[Corner].V = Texels[Corner][1];
			}
			++FromVram;
			PushPrimitive(Into.Get(bSemi ? BlendOf(Page.Blend) : EBlend::Opaque, {}), Corners, 4, Look);
		}

		/** The stage's backdrop: the dome's packets, then the panoramas, the second first (AddBackdrop). */
		void AddBattleBackdrop(FCollector& Into, const FBattleShowFrame& Frame, const FVram& Vram)
		{
			// The bands reach a screen's width past either side, for a window wider than the original's screen.
			constexpr int32 Beyond = FieldBackdropWidth;
			std::optional<std::array<int16, 4>> Window;
			EBlendMode PageBlend = EBlendMode::Average;
			for (const FBattleDomePacket& Packet : Frame.Backdrop.Dome)
			{
				if (Packet.bDrawMode)
				{
					Window = Packet.Window[2] != 0 ? std::optional<std::array<int16, 4>>(Packet.Window) : std::nullopt;
					PageBlend = FTexturePage::FromAttribute(Packet.DrawPage).Blend;
					continue;
				}
				const FFieldBackdropQuad& Quad = Packet.Quad;
				std::array<std::array<float, 2>, 4> Screen{};
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					Screen[Corner] = {static_cast<float>(Quad.Corners[Corner][0]), static_cast<float>(Quad.Corners[Corner][1])};
				}
				if (Quad.Kind == FFieldBackdropQuad::EKind::Textured)
				{
					PageBlend = FTexturePage::FromAttribute(Quad.TexturePage).Blend;
				}
				else
				{
					for (std::size_t Corner = 0; Corner < 4; ++Corner)
					{
						Screen[Corner][0] = Quad.Corners[Corner][0] == 0 ? static_cast<float>(-Beyond) : Screen[Corner][0] + static_cast<float>(Beyond);
					}
				}
				AddBattleBackdropQuad(Into, Frame, Vram, Quad, Screen, Packet.bSemiTransparent, Window, PageBlend);
			}
			for (std::size_t Slot = Frame.Backdrop.Panoramas.size(); Slot-- > 0;)
			{
				DrawFieldBackdrop(Frame.Backdrop.Panoramas[Slot], -Beyond, FieldBackdropWidth + Beyond, BackdropQuads);
				for (const FFieldBackdropQuad& Quad : BackdropQuads)
				{
					std::array<std::array<float, 2>, 4> Screen{};
					for (std::size_t Corner = 0; Corner < 4; ++Corner)
					{
						Screen[Corner] = {static_cast<float>(Quad.Corners[Corner][0]), static_cast<float>(Quad.Corners[Corner][1])};
					}
					AddBattleBackdropQuad(Into, Frame, Vram, Quad, Screen, false, std::nullopt, PageBlend);
				}
			}
		}

		/** One link of the frame's drawing order (not the fade's or the HUD's). */
		void AddBattleLink(FCollector& Into, const FBattleShowFrame& Frame, const FVram& Vram, const FBattleShowLink& Link)
		{
			if (Report != nullptr)
			{
				// What a frame report's notes say the drawing is of (a quad says more for itself).
				Report->Who = "battle link of kind " + std::to_string(static_cast<int>(Link.Kind)) + " #" + std::to_string(Link.Index);
			}
			switch (Link.Kind)
			{
			case EBattleShowLink::Quad:
				if (Link.Index < Frame.Quads.size()) AddBattleQuad(Into, Frame, Vram, Frame.Quads[Link.Index]);
				break;
			case EBattleShowLink::Triangle:
				if (Link.Index < Frame.Triangles.size()) AddBattleTriangle(Into, Frame.Triangles[Link.Index]);
				break;
			case EBattleShowLink::Object:
				if (Frame.Objects != nullptr && Link.Index < Frame.Objects->Links.size()) AddBattleObject(Into, Frame, Vram, Frame.Objects->Links[Link.Index]);
				break;
			case EBattleShowLink::Backdrop:
				AddBattleBackdrop(Into, Frame, Vram);
				break;
			case EBattleShowLink::Tile:
				if (Link.Index < Frame.Tiles.size()) AddBattleTile(Into, Frame, Frame.Tiles[Link.Index]);
				break;
			case EBattleShowLink::Line:
				if (Link.Index < Frame.Lines.size()) AddBattleLine(Into, Frame.Lines[Link.Index]);
				break;
			case EBattleShowLink::ScreenQuad:
				if (Link.Index < Frame.ScreenQuads.size()) AddBattleScreenQuad(Into, Frame, Vram, Frame.ScreenQuads[Link.Index]);
				break;
			case EBattleShowLink::ModelPolygon:
				if (Link.Index < Frame.ModelPolygons.size()) AddBattleModelPolygon(Into, Frame, Vram, Frame.ModelPolygons[Link.Index]);
				break;
			case EBattleShowLink::Fade:
			case EBattleShowLink::Hud:
				break;
			}
		}

		/** The fade layer: a tile from (-32, -32) to (320, 240), semi-transparent in its mode, over the whole display (BuildBattleFade). */
		void PushBattleFade(FCollector& Into, const FBattleShowFrame& Frame)
		{
			FLook Look;
			Look.Flags = FlagSemi;
			Look.Spans = 1.0f;
			std::array<FCorner, 4> Corners{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				Corners[Corner].Pos = {(Corner & 1) != 0 ? 320.0f : -32.0f, (Corner & 2) != 0 ? 240.0f : -32.0f, 0.0f};
				Corners[Corner].Color = {Frame.Fade.Color[0], Frame.Fade.Color[1], Frame.Fade.Color[2]};
			}
			PushPrimitive(Into.Get(BlendOf(static_cast<EBlendMode>(Frame.Fade.Mode & 3)), {}), Corners, 4, Look);
		}

		/** The HUD's primitives as a 2D list, as the game draws them (BattleView.cpp: FMenuDrawBuilder, without the player's button pictures). */
		void PushBattleHud(FCollector& Into, const FBattleShowFrame& Frame, const FVram& Vram)
		{
			HudFrame.Primitives.assign(Frame.Hud.Primitives.begin(), Frame.Hud.Primitives.end());
			HudFrame.TextButtons.assign(Frame.Hud.TextButtons.begin(), Frame.Hud.TextButtons.end());
			HudFrame.Number = Frame.Step + 1;
			HudBuilder.Build(HudFrame, nullptr, 1.0f, HudList);
			PushDrawList(Into, Vram, HudList);
		}

		/**
		 * The field's panorama (FFieldFrame::Backdrop) as Weltall's renderer draws it (Rendering/FieldFrameGeometry.cpp,
		 * AddFieldBackdrop): its colour bands and strip over the screen's columns and a screen's width past either side, far
		 * behind anything the field draws, each corner where it projects onto its screen pixel; the strip's texels raw, run
		 * to the far column and row themselves. Unlit, at the far end of the depth (it is the first thing of its table entry).
		 */
		/**
		 * The sprites' spawned children's models (FFieldFrame::SpriteModels): each polygon the original draws (bDrawn), its
		 * corners through its model's matrix (model to view as the GTE drew it), its packet's code, page and CLUT, its
		 * colours (depth-cued in fog: its texels modulated even where the packet draws them raw), as Weltall's renderer
		 * draws them (Source/Weltall/Private/Rendering/FieldSpriteModelDraw.cpp); textured ones as the scenery (pages with
		 * the pack's pictures).
		 */
		void AddFieldSpriteModels(FCollector& Into, const FVram& Vram, const FFieldFrame& Frame)
		{
			const FFieldSpriteModelsFrame& Models = Frame.SpriteModels;
			for (const FFieldSpriteModelPolygon& Polygon : Models.Polygons)
			{
				if (!Polygon.bDrawn || Polygon.Model >= Models.Models.size())
				{
					continue;
				}
				const FMdlPrimitiveTraits Traits = MdlPrimitiveTraits(Polygon.Type);
				const int Count = Polygon.CornerCount == 4 ? 4 : 3;
				std::array<FCorner, 4> Corners{};
				for (std::size_t Corner = 0; Corner < static_cast<std::size_t>(Count); ++Corner)
				{
					Corners[Corner].Pos = ToGodot(ViewPoint(Models.Models[Polygon.Model].Matrix, Polygon.Corners[Corner]));
					Corners[Corner].Color = ColorOf(Polygon.Colors[Traits.bGouraud ? Corner : 0]);
					Corners[Corner].U = Polygon.Uvs[Corner].U;
					Corners[Corner].V = Polygon.Uvs[Corner].V;
				}
				const bool bSemi = (Polygon.Code & 2) != 0;
				const bool bRaw = (Polygon.Code & 1) != 0 && !Polygon.bFogged;
				const FTexturePage Page = FTexturePage::FromAttribute(Polygon.TexturePage);
				const FClutPosition Clut = FClutPosition::FromAttribute(Polygon.Clut);
				FLook Look;
				EBlend Blend = EBlend::Opaque;
				if (Traits.bTextured)
				{
					SetPage(Look, Page, Clut);
					Blend = bSemi ? BlendOf(Page.Blend) : EBlend::Opaque;
				}
				else if (bSemi)
				{
					Blend = EBlend::Average;
				}
				Look.Flags = (bRaw && Traits.bTextured ? FlagRaw : 0.0f) + (bSemi ? FlagSemi : 0.0f);
				if (Report != nullptr)
				{
					Report->Who = "sprite's child model " + std::to_string(Polygon.Model);
				}
				PushScenery(Into, Vram, Corners, Count, Look, Traits.bTextured, Page, Clut, Blend);
			}
		}

		/**
		 * What the field's gears draw (FFieldFrame::Gears): each entry of the frame's Order of kind Gear, as Weltall's renderer
		 * lays them out (Source/Weltall/Private/Rendering/FieldGearDraw.cpp): a bone's part polygon by its object's matrix
		 * (model to view as the GTE drew it, or its fine matrix), its packet's code and texture, the colours the tick lit it
		 * with; a floor shadow as the sprites' blob on a quad of the model's half-sizes; a cloth's triangle in the world
		 * (through the view) or in its placed model's space. Models as the scenery (pages with the pack's pictures), the
		 * shadow as the characters' shadows are (VRAM, subtractive).
		 */
		void AddFieldGears(FCollector& Into, const FVram& Vram, const FFieldFrame& Frame)
		{
			const FFieldGearsFrame& Gears = Frame.Gears;
			if (Gears.Items.size() != Gears.Objects.size())
			{
				return;
			}
			if (Report != nullptr)
			{
				Report->Who = "field gear";
			}
			// Each polygon's item: the layout gives each item its run of polygons.
			std::vector<int> ItemOf(Gears.Polygons.size(), -1);
			for (std::size_t Item = 0; Item < Gears.Items.size(); ++Item)
			{
				const FFieldGearLayoutItem& Laid = Gears.Items[Item];
				for (uint32 Number = 0; Number < Laid.PolygonCount && Laid.FirstPolygon + Number < ItemOf.size(); ++Number)
				{
					ItemOf[Laid.FirstPolygon + Number] = static_cast<int>(Item);
				}
			}
			for (const FFieldDrawItem& Entry : Frame.Order)
			{
				if (Entry.Kind != EFieldDrawKind::Gear)
				{
					continue;
				}
				if (Entry.Gear == EFieldGearDraw::Cloth)
				{
					if (Entry.Index >= Gears.Cloths.size())
					{
						continue;
					}
					const FGearDrawnClothTriangle& Triangle = Gears.Cloths[Entry.Index];
					const auto Space = std::find_if(Gears.ClothSpaces.begin(), Gears.ClothSpaces.end(),
						[&Triangle](const FFieldGearClothSpace& Placed) { return Placed.Slot == Triangle.Slot; });
					std::array<FCorner, 4> Corners{};
					for (std::size_t Corner = 0; Corner < 3; ++Corner)
					{
						const FGteVector& Point = Triangle.Points[Corner];
						const std::array<float, 3> At = Space != Gears.ClothSpaces.end()
							? Apply(Space->Space, Point[0], Point[1], Point[2]) : ViewPoint(Frame.View.View, Point);
						Corners[Corner].Pos = ToGodot(At);
						Corners[Corner].Color = ColorOf(Triangle.Colors[Corner]);
						Corners[Corner].U = Triangle.Uvs[Corner].U;
						Corners[Corner].V = Triangle.Uvs[Corner].V;
					}
					// A cloth's page and CLUT are made from its place: their high y bits are set only for one in the port's rows.
					const FTexturePage Page = FTexturePage::FromPortAttribute(Triangle.TexturePage);
					const FClutPosition Clut = FClutPosition::FromPortAttribute(Triangle.Clut);
					const bool bSemi = (GearClothCode & 2) != 0;
					FLook Look;
					SetPage(Look, Page, Clut);
					Look.Flags = ((GearClothCode & 1) != 0 ? FlagRaw : 0.0f) + (bSemi ? FlagSemi : 0.0f);
					PushScenery(Into, Vram, Corners, 3, Look, true, Page, Clut, bSemi ? BlendOf(Page.Blend) : EBlend::Opaque);
					continue;
				}
				if (Entry.Index >= ItemOf.size() || ItemOf[Entry.Index] < 0)
				{
					continue;
				}
				const FFieldGearLayoutItem& Laid = Gears.Items[static_cast<std::size_t>(ItemOf[Entry.Index])];
				const FFieldGearObject& Object = Gears.Objects[static_cast<std::size_t>(ItemOf[Entry.Index])];
				const FFieldGearPolygon& Polygon = Gears.Polygons[Entry.Index];
				const auto ToView = [&Object](const FGteVector& Point)
				{
					return Object.bFine ? Apply(Object.Fine, Point[0], Point[1], Point[2]) : ViewPoint(Object.Matrix, Point);
				};
				if (Laid.Packets == nullptr)
				{
					// The floor shadow: the sprites' blob on a quad of the model's half-sizes, on its floor (FieldGearShadow).
					using namespace FieldGearShadow;
					const int16 X = Laid.HalfWidth, Z = Laid.HalfDepth;
					const std::array<FGteVector, 4> Quad{{{X, 0, Z}, {static_cast<int16>(-X), 0, Z}, {X, 0, static_cast<int16>(-Z)},
						{static_cast<int16>(-X), 0, static_cast<int16>(-Z)}}};
					std::array<std::array<float, 3>, 4> Places{};
					for (std::size_t Corner = 0; Corner < 4; ++Corner)
					{
						Places[Corner] = ToGodot(ToView(Quad[Corner]));
					}
					const std::array<std::array<int16, 2>, 4> Texels{{{FirstTexel, FirstRow}, {LastTexel, FirstRow}, {FirstTexel, LastRow}, {LastTexel, LastRow}}};
					const FMdlColor& Shade = Polygon.Colors[0];
					PushViewQuadAt(Into, Vram, Places, Texels, TexturePage, Clut, false, static_cast<uint32>(Shade.R | Shade.G << 8 | Shade.B << 16),
						(Code & 1) != 0, (Code & 2) != 0, false, false);
					continue;
				}
				const FMdlPart& Part = *Laid.Part;
				const uint32 Number = Entry.Index - Laid.FirstPolygon;
				if (Number >= Part.Primitives.size())
				{
					continue;
				}
				const FMdlPrimitive& Primitive = Part.Primitives[Number];
				const FMdlPrimitiveTraits& Traits = Primitive.Traits();
				const uint8 Code = Laid.Packets->Packets[Number].Code;
				const FMdlTextureState& Texture = Laid.Packets->Textures[Number];
				std::array<FCorner, 4> Corners{};
				for (std::size_t Corner = 0; Corner < Traits.Corners; ++Corner)
				{
					Corners[Corner].Pos = ToGodot(ToView(Part.Vertices[Primitive.Vertices[Corner]]));
					Corners[Corner].Color = ColorOf(Polygon.Colors[Traits.bGouraud ? Corner : 0]);
					Corners[Corner].U = Primitive.Uvs[Corner].U;
					Corners[Corner].V = Primitive.Uvs[Corner].V;
				}
				const bool bSemi = (Code & 2) != 0;
				const FTexturePage Page = Laid.bPortRows ? FTexturePage::FromPortAttribute(Texture.TexturePage) : FTexturePage::FromAttribute(Texture.TexturePage);
				const FClutPosition Clut = Laid.bPortRows ? FClutPosition::FromPortAttribute(Texture.Clut) : FClutPosition::FromAttribute(Texture.Clut);
				FLook Look;
				EBlend Blend = EBlend::Opaque;
				if (Traits.bTextured)
				{
					SetPage(Look, Page, Clut);
					Blend = bSemi ? BlendOf(Page.Blend) : EBlend::Opaque;
				}
				else if (bSemi)
				{
					// The GPU blends an untextured one by the last textured page's mode, which is not tracked here: average (as the battle's).
					Blend = EBlend::Average;
				}
				Look.Flags = ((Code & 1) != 0 && Traits.bTextured ? FlagRaw : 0.0f) + (bSemi ? FlagSemi : 0.0f);
				PushScenery(Into, Vram, Corners, Traits.Corners, Look, Traits.bTextured, Page, Clut, Blend);
			}
		}

		void AddFieldBackdrop(FCollector& Into, const FVram& Vram, const FFieldFrame& Frame)
		{
			constexpr int32 Beyond = FieldBackdropWidth;
			constexpr float Depth = 65536.0f;
			DrawFieldBackdrop(Frame.Backdrop, -Beyond, FieldBackdropWidth + Beyond, BackdropQuads);
			const float Scale = Depth / static_cast<float>(std::max<uint16>(Frame.View.ProjectionDistance, 1));
			Into.bUnlit = true;
			for (const FFieldBackdropQuad& Quad : BackdropQuads)
			{
				FLook Look;
				std::array<FCorner, 4> Corners{};
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					Corners[Corner].Pos = ToGodot({static_cast<float>(Quad.Corners[Corner][0] - FieldScreenCenterX) * Scale,
						static_cast<float>(Quad.Corners[Corner][1] - FieldScreenCenterY) * Scale, Depth});
					const std::size_t Tint = Quad.Kind == FFieldBackdropQuad::EKind::Graded ? Corner : 0;
					Corners[Corner].Color = {Quad.Colors[Tint][0], Quad.Colors[Tint][1], Quad.Colors[Tint][2]};
					Corners[Corner].U = Quad.Texels[Corner][0];
					Corners[Corner].V = Quad.Texels[Corner][1];
				}
				if (Quad.Kind != FFieldBackdropQuad::EKind::Textured)
				{
					PushPrimitive(Into.Get(EBlend::Opaque, {}), Corners, 4, Look);
					continue;
				}
				const FTexturePage Page = FTexturePage::FromAttribute(Quad.TexturePage);
				const FClutPosition Clut = FClutPosition::FromAttribute(Quad.Clut);
				SetPage(Look, Page, Clut);
				Look.Flags = FlagRaw;
				const float MinU = std::min(Corners[0].U, Corners[1].U), MaxU = std::max(Corners[0].U, Corners[1].U);
				const float MinV = std::min(Corners[0].V, Corners[2].V), MaxV = std::max(Corners[0].V, Corners[2].V);
				Look.Clamp = {MinU, MinV, std::max(MinU, MaxU - 1.0f), std::max(MinV, MaxV - 1.0f)};
				PushTextured(Into, FrameHits, Vram, EBlend::Opaque, Corners, 4, Look, Page, Clut, true, false, nullptr);
			}
			Into.bUnlit = false;
		}

		// ---- The World Map program's frame. Adapted from Weltall's own renderer (MIT): Source/Weltall/Private/Rendering/
		// WorldMapFrameDraw.cpp (the polygons, already in view space, in the order the GPU draws them; the projection about
		// the 216-line screen's centre, below its middle; the horizon's band cut where its texture window wraps; a one-sided
		// polygon's triangle dropped where it winds away from the eye; an untextured semi-transparent polygon blending as the
		// last textured one set the GPU, ScenePolygonOrder.cpp), Screens/WorldMapView.cpp (the minimap and the windows, the
		// fade over the scene's rows, the program's own fades over a picture). Drawn as the battle is: unlit, each polygon at
		// its place in the order (C1's w), the painter's order of the reference renderer's PaintersOrder. ----

		/** The world map's screen: 320 x 216, its centre below the middle. */
		static constexpr FScreenSize WorldMapScreen{320, 216};
		/** The last BuildWorld's world map polygons by what drew them (EWorldMapLayer), and the one-sided triangles it dropped. */
		std::array<int, 11> MapLayers{};
		int MapPolygons = 0, MapOneSidedDropped = 0;
		/** The key of the picture of the screen before the world map started (the display gives it as it gives the field's). */
		int MapScreenBefore = 0;
		/** The key of the picture of the screen before the battle running now (BattlePictureKey); 0 none. */
		int BattleScreenBefore = 0;
		/** The 2D lists pushed now are of a screen ListScale times as high as the one the layer is laid on (1: the same). */
		float ListScale = 1.0f;

		const FWorldMapProgram* WorldMap() const { return Loop ? Loop->WorldMap() : nullptr; }

		/** The map's latest frame, null before its first. */
		const FWorldMapFrame* MapFrame() const
		{
			const FWorldMapProgram* Map = WorldMap();
			return Map != nullptr ? Map->LatestFrame() : nullptr;
		}

		/** The picture of the screen before the world map started has a key of its own beside the field's counts of pictures. */
		static int MapPictureKey(uint32 ProgramRuns) { return 0x40000000 | static_cast<int>(ProgramRuns & 0xFFFFFF); }

		/**
		 * Lines: the screen the frame's form projects onto (the world map's 216, the arena's 218: main.gd's scene_lines);
		 * ColumnScale: the display's columns over the frame's (the arena's winner screen counts 640 across the same width).
		 */
		void BeginMapDrawing(const FWorldMapFrame& Frame, float Lines = static_cast<float>(WorldMapScreen.Height), float ColumnScale = 1.0f)
		{
			bBattleDrawing = true;
			bBattleToScreen = false;
			BattleWhole = BattleClipped = BattleBehind = 0;
			OrderCount = 0;
			CurrentOrder = 0.0f;
			BattleDistance = static_cast<float>(std::max<int32>(Frame.ProjectionDistance, 1));
			// The camera projects about the middle of the screen's lines (main.gd: scene_lines); the frame's centre lies
			// elsewhere (below the middle): each point moves across and down in proportion to its depth (PlaceWorldMapObjects).
			// Across, the frame's columns are scaled to the display's (its rows' x times ColumnScale, as there).
			BattleColumnScale = ColumnScale;
			BattleAcross = (static_cast<float>(Frame.ScreenCenterX) * ColumnScale - WorldMapScreen.Width / 2.0f) / BattleDistance;
			BattleLower = (static_cast<float>(Frame.ScreenCenterY) - Lines / 2.0f) / BattleDistance;
			MapLayers = {};
			MapPolygons = MapOneSidedDropped = 0;
			MapAnimatedPieces = MapAnimatedHd = 0;
		}

		/** A piece of a polygon as drawn: its corners, their texels, the texels it samples, whether its far edges lie one past them. */
		struct FMapPiece
		{
			std::array<std::array<float, 3>, 4> View{};
			std::array<std::array<float, 2>, 4> Texels{};
			std::array<float, 2> TexelMin{}, TexelMax{};
			bool bOnePast = false;
		};

		/**
		 * A quad whose texels repeat in a texture window across u (the horizon's band): cut where u wraps, each piece sampling
		 * within the window (WindowPieces, unscrolled: a tick's frame as it is). How many pieces.
		 */
		static int MapWindowPieces(const FWorldMapPolygon& Polygon, std::array<FMapPiece, 2>& Pieces)
		{
			const float Width = Polygon.WindowWidth;
			float Wrapped = std::fmod(Polygon.TexCoords[0][0], Width);
			if (Wrapped < 0.0f)
			{
				Wrapped += Width;
			}
			const float Across = Polygon.TexCoords[1][0] - Polygon.TexCoords[0][0];
			if (Across <= 0.0f)
			{
				return 0;
			}
			const float Split = std::clamp((Width - Wrapped) / Across, 0.0f, 1.0f);
			const auto Lerp = [](const std::array<float, 3>& A, const std::array<float, 3>& B, float T) {
				return std::array<float, 3>{A[0] + (B[0] - A[0]) * T, A[1] + (B[1] - A[1]) * T, A[2] + (B[2] - A[2]) * T};
			};
			const std::array<float, 3> Top = Lerp(Polygon.View[0], Polygon.View[1], Split);
			const std::array<float, 3> Bottom = Lerp(Polygon.View[2], Polygon.View[3], Split);
			const float V0 = Polygon.TexCoords[0][1], V1 = Polygon.TexCoords[2][1];
			Pieces[0] = {{Polygon.View[0], Top, Polygon.View[2], Bottom}, {{{Wrapped, V0}, {Width, V0}, {Wrapped, V1}, {Width, V1}}},
				{std::floor(Wrapped), static_cast<float>(Polygon.TexelMin[1])}, {Width - 1.0f, static_cast<float>(Polygon.TexelMax[1])}, true};
			if (Split >= 1.0f)
			{
				return 1;
			}
			const float Rest = Wrapped + Across - Width;
			Pieces[1] = {{Top, Polygon.View[1], Bottom, Polygon.View[3]}, {{{0.0f, V0}, {Rest, V0}, {0.0f, V1}, {Rest, V1}}},
				{0.0f, static_cast<float>(Polygon.TexelMin[1])}, {std::max(Rest - 1.0f, 0.0f), static_cast<float>(Polygon.TexelMax[1])}, true};
			return 2;
		}

		/** The last BuildWorld's scenery pieces whose texels the program animates, and of them those drawn from a picture of the pack. */
		int MapAnimatedPieces = 0, MapAnimatedHd = 0;

		/** Whether a piece's texels lie (partly) in a VRAM rectangle the program's animations have written (MapAnimated). */
		bool TexelsAnimated(const FTexturePage& Page, const FMapPiece& Piece) const
		{
			if (MapAnimated.empty() || Page.Y >= FVram::Height)
			{
				return false;
			}
			const int Per = TexelsPerUnit(Page.Depth);
			const int Left = Page.X + static_cast<int>(Piece.TexelMin[0]) / Per, Right = Page.X + static_cast<int>(Piece.TexelMax[0]) / Per;
			const int Top = Page.Y + static_cast<int>(Piece.TexelMin[1]), Bottom = Page.Y + static_cast<int>(Piece.TexelMax[1]);
			return std::any_of(MapAnimated.begin(), MapAnimated.end(), [&](const FVramRect& Rect) {
				return Rect.X <= Right && Left < Rect.X + Rect.Width && Rect.Y <= Bottom && Top < Rect.Y + Rect.Height;
			});
		}

		/** Whether a triangle (view space: x right, y down, z ahead) winds clockwise on the screen: it faces the eye (FieldScene.usf). */
		static bool FacesEye(const std::array<float, 3>& A, const std::array<float, 3>& B, const std::array<float, 3>& C)
		{
			const std::array<float, 3> Cross{B[1] * C[2] - B[2] * C[1], B[2] * C[0] - B[0] * C[2], B[0] * C[1] - B[1] * C[0]};
			return A[0] * Cross[0] + A[1] * Cross[1] + A[2] * Cross[2] > 0.0f;
		}

		/**
		 * One piece of a world map polygon (Count corners: 3, or a quad's 4) into the scene at the next place in the order:
		 * untextured (flat or a colour a corner), or textured by what drew it: a sprite's part through the pack's lookup
		 * (its packet's texels, which end at the last one, over its whole quad; as the field's sprites), a shadow from VRAM
		 * (the game's own, as the battle's), the terrain, the place models and the gears from the page with the pack's
		 * pictures laid in (as the field's scenery), the rest (trees, clouds, particles, the horizon's band, the arena's
		 * effects) through the pack's lookup by picture.
		 */
		void PushMapPiece(FCollector& Into, const FVram& Vram, const FWorldMapPolygon& Polygon, const FMapPiece& Piece, int Count, EBlendMode UntexturedBlend)
		{
			if (!InFront(Piece.View, Count))
			{
				return;
			}
			NextOrder();
			FLook Look;
			Look.Order = CurrentOrder;
			std::array<FCorner, 4> Corners{};
			for (int Corner = 0; Corner < Count; ++Corner)
			{
				const std::size_t At = static_cast<std::size_t>(Corner);
				const FDrawColor& Color = Polygon.Colors[Polygon.bGouraud ? At : 0];
				Corners[At].Pos = BattlePlace(Piece.View[At]);
				Corners[At].Color = {Color.R, Color.G, Color.B};
				Corners[At].U = Piece.Texels[At][0];
				Corners[At].V = Piece.Texels[At][1];
			}
			if (!Polygon.bTextured)
			{
				Look.Flags = Polygon.bSemiTransparent ? FlagSemi : 0.0f;
				PushPrimitive(Into.Get(Polygon.bSemiTransparent ? BlendOf(UntexturedBlend) : EBlend::Opaque, {}), Corners, Count, Look);
				return;
			}
			// A page and CLUT in VRAM's port rows are read with their high y bits.
			const FTexturePage Page = Polygon.bPortRows ? FTexturePage::FromPortAttribute(Polygon.TexturePage) : FTexturePage::FromAttribute(Polygon.TexturePage);
			const FClutPosition Clut = Polygon.bPortRows ? FClutPosition::FromPortAttribute(Polygon.Clut) : FClutPosition::FromAttribute(Polygon.Clut);
			SetPage(Look, Page, Clut);
			Look.Flags = (Polygon.bRaw ? FlagRaw : 0.0f) + (Polygon.bSemiTransparent ? FlagSemi : 0.0f);
			Look.Clamp = {Piece.TexelMin[0], Piece.TexelMin[1], Piece.TexelMax[0], Piece.TexelMax[1]};
			const EBlend Blend = Polygon.bSemiTransparent ? BlendOf(Page.Blend) : EBlend::Opaque;
			switch (Polygon.Layer)
			{
			case EWorldMapLayer::Sprite:
				PushTextured(Into, FrameHits, Vram, Blend, Corners, Count, Look, Page, Clut, Piece.bOnePast, true, nullptr, ETally::Sprite);
				return;
			case EWorldMapLayer::Shadow:
				++FromVram;
				PushPrimitive(Into.Get(Blend, {}), Corners, Count, Look);
				return;
			case EWorldMapLayer::Terrain:
			case EWorldMapLayer::Model:
			case EWorldMapLayer::Gear:
				if (TexelsAnimated(Page, Piece))
				{
					// Texels the program's animations write (the water's tiles): a page's picture would stand still. Looked up
					// upload by upload as Beetle names each frame, the pack has pictures of only some of the frames (measured on
					// the user's save: from 5 % to 83 % of these pieces by the frame), so the water would switch between the
					// pack's look and the original's as it animates; drawn from VRAM, it animates as the original does.
					// XENO_ANIMATED_PACK=1 looks them up (Beetle's way), for comparisons.
					++MapAnimatedPieces;
					static const bool bAnimatedPack = std::getenv("XENO_ANIMATED_PACK") != nullptr;
					if (bAnimatedPack)
					{
						const int Before = FromVram;
						PushTextured(Into, FrameHits, Vram, Blend, Corners, Count, Look, Page, Clut, Piece.bOnePast, false, nullptr, ETally::None, !Piece.bOnePast);
						MapAnimatedHd += FromVram == Before ? 1 : 0;
						return;
					}
					++FromVram;
					PushPrimitive(Into.Get(Blend, {}), Corners, Count, Look);
					return;
				}
				PushScenery(Into, Vram, Corners, Count, Look, true, Page, Clut, Blend);
				return;
			default:
				if (Page.Y >= FVram::Height)
				{
					++FromVram;
					PushPrimitive(Into.Get(Blend, {}), Corners, Count, Look);
					return;
				}
				PushTextured(Into, FrameHits, Vram, Blend, Corners, Count, Look, Page, Clut, Piece.bOnePast, false, nullptr, ETally::None, !Piece.bOnePast);
				return;
			}
		}

		/** A polygon of the frame: its pieces (the band's cut at the window), a one-sided polygon's triangles that face away left out. */
		void AddMapPolygon(FCollector& Into, const FVram& Vram, const FWorldMapPolygon& Polygon, EBlendMode UntexturedBlend)
		{
			++MapPolygons;
			++MapLayers[std::min<std::size_t>(static_cast<std::size_t>(Polygon.Layer), MapLayers.size() - 1)];
			std::array<FMapPiece, 2> Pieces;
			int PieceCount = 1;
			if (Polygon.WindowWidth != 0 && Polygon.CornerCount == 4)
			{
				PieceCount = MapWindowPieces(Polygon, Pieces);
			}
			else
			{
				// The packet's own texels, as the GPU interpolates them across the polygon (a sprite's part's end at its last texel).
				// It samples the texels the frame says it samples (TexelMin to TexelMax, inclusive; the reference renderer's
				// clamp, WorldMapFrameDraw.cpp SetTexels); where the packet's far edge lies past them (the arena's effect
				// sprites run edge to edge, U + size), the far edges are one past the last texel.
				FMapPiece& Piece = Pieces[0];
				Piece.View = Polygon.View;
				Piece.TexelMin = {static_cast<float>(Polygon.TexelMin[0]), static_cast<float>(Polygon.TexelMin[1])};
				Piece.TexelMax = {static_cast<float>(Polygon.TexelMax[0]), static_cast<float>(Polygon.TexelMax[1])};
				Piece.bOnePast = false;
				for (std::size_t Corner = 0; Corner < Polygon.CornerCount && Corner < 4; ++Corner)
				{
					Piece.Texels[Corner] = {static_cast<float>(Polygon.U[Corner]), static_cast<float>(Polygon.V[Corner])};
					Piece.bOnePast = Piece.bOnePast || Piece.Texels[Corner][0] > Piece.TexelMax[0] || Piece.Texels[Corner][1] > Piece.TexelMax[1];
				}
				if (Polygon.Layer == EWorldMapLayer::Sprite && Polygon.CornerCount == 4)
				{
					// A sprite's part: the PS1 shows its own texels, first to last (TexelMin to TexelMax), across its quad, mirrored or
					// not; the packet of a part mirrored on screen starts a column lower only because the GPU, stepping u down,
					// shows each texel a column on (WorldMapDrawing.cpp, DrawWorldMapSprite). As the field's sprites: the last
					// texel at the far edge (corners 1 and 3 far, 2 and 3 low).
					for (std::size_t Corner = 0; Corner < 4; ++Corner)
					{
						Piece.Texels[Corner] = {static_cast<float>((Corner & 1) != 0 ? Polygon.TexelMax[0] : Polygon.TexelMin[0]),
							static_cast<float>((Corner & 2) != 0 ? Polygon.TexelMax[1] : Polygon.TexelMin[1])};
					}
					Piece.TexelMin = {static_cast<float>(Polygon.TexelMin[0]), static_cast<float>(Polygon.TexelMin[1])};
					Piece.TexelMax = {static_cast<float>(Polygon.TexelMax[0]), static_cast<float>(Polygon.TexelMax[1])};
				}
			}
			const int Count = Polygon.CornerCount == 4 ? 4 : 3;
			for (int Index = 0; Index < PieceCount; ++Index)
			{
				const FMapPiece& Piece = Pieces[static_cast<std::size_t>(Index)];
				if (!Polygon.bOneSided)
				{
					PushMapPiece(Into, Vram, Polygon, Piece, Count, UntexturedBlend);
					continue;
				}
				// Its triangles as drawn, (0, 1, 2) and a quad's (1, 3, 2): each only where it faces the eye.
				const bool bFirst = FacesEye(Piece.View[0], Piece.View[1], Piece.View[2]);
				const bool bSecond = Count == 4 && FacesEye(Piece.View[1], Piece.View[3], Piece.View[2]);
				MapOneSidedDropped += (bFirst ? 0 : 1) + (Count == 4 && !bSecond ? 1 : 0);
				if (bFirst && (Count == 3 || bSecond))
				{
					PushMapPiece(Into, Vram, Polygon, Piece, Count, UntexturedBlend);
				}
				else if (bFirst || bSecond)
				{
					// One of a quad's triangles: its corners as a triangle of their own, in the same winding.
					const std::array<std::size_t, 3> Kept = bFirst ? std::array<std::size_t, 3>{0, 1, 2} : std::array<std::size_t, 3>{1, 3, 2};
					FMapPiece Triangle = Piece;
					for (std::size_t Corner = 0; Corner < 3; ++Corner)
					{
						Triangle.View[Corner] = Piece.View[Kept[Corner]];
						Triangle.Texels[Corner] = Piece.Texels[Kept[Corner]];
					}
					PushMapPiece(Into, Vram, Polygon, Triangle, 3, UntexturedBlend);
				}
			}
		}

		/** The frame's polygons in the GPU's order into the scene, projected onto Lines lines, its columns scaled by ColumnScale. */
		void AddMapScene(FCollector& Into, const FVram& Vram, const FWorldMapFrame& Frame, float Lines = static_cast<float>(WorldMapScreen.Height),
			float ColumnScale = 1.0f)
		{
			BeginMapDrawing(Frame, Lines, ColumnScale);
			// An untextured semi-transparent polygon blends as the last textured one drawn before it set the GPU.
			EBlendMode Current = EBlendMode::Average;
			for (const FWorldMapPolygon& Polygon : Frame.Polygons)
			{
				if (Polygon.bTextured)
				{
					Current = (Polygon.bPortRows ? FTexturePage::FromPortAttribute(Polygon.TexturePage) : FTexturePage::FromAttribute(Polygon.TexturePage)).Blend;
				}
				if (Report != nullptr)
				{
					// Terrain, sky, horizon, sprite, model, shadow, billboard, cloud, particle, gear, effect (FFrameInfo::MapLayers).
					Report->Who = "map polygon of layer " + std::to_string(static_cast<int>(Polygon.Layer));
				}
				AddMapPolygon(Into, Vram, Polygon, Current);
			}
			EndBattleDrawing();
		}

		/**
		 * A grey drawn over the whole display, the GPU subtracting it from what lies below (Blend 2) or adding it (1): one of
		 * the program's own fades over its picture (FWorldMapFadeFrame), across the picture's rows.
		 */
		void PushMapDarkening(FCollector& Into, int32 Level, int32 Blend)
		{
			const uint8 Clamped = static_cast<uint8>(std::clamp(Level, 0, 255));
			FLook Look;
			Look.Flags = FlagSemi;
			Look.Spans = 1.0f;
			std::array<FCorner, 4> Corners{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				Corners[Corner].Pos = {(Corner & 1) != 0 ? static_cast<float>(WorldMapScreen.Width) : 0.0f, (Corner & 2) != 0 ? static_cast<float>(WorldMapScreen.Height) : 0.0f, 0.0f};
				Corners[Corner].Color = {Clamped, Clamped, Clamped};
			}
			Mix(static_cast<uint32>(Clamped) | static_cast<uint32>(Blend) << 8);
			++ScreenPrimitives;
			PushPrimitive(Into.Get(BlendOf(static_cast<EBlendMode>(Blend & 3)), {}), Corners, 4, Look);
		}

		/** The screen before the world map started, over the whole display, as the display showed it (once it has given it). */
		bool PushMapScreenBefore(FCollector& Into)
		{
			if (ScreenPictures.count(MapScreenBefore) == 0)
			{
				return false;
			}
			FLook Look;
			Look.Spans = 1.0f;
			std::array<FCorner, 4> Corners{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				Corners[Corner].Pos = {(Corner & 1) != 0 ? static_cast<float>(WorldMapScreen.Width) : 0.0f, (Corner & 2) != 0 ? static_cast<float>(WorldMapScreen.Height) : 0.0f, 0.0f};
				Corners[Corner].U = (Corner & 1) != 0 ? 1.0f : 0.0f;
				Corners[Corner].V = (Corner & 2) != 0 ? 1.0f : 0.0f;
			}
			Mix(static_cast<uint32>(MapScreenBefore));
			++ScreenPrimitives;
			PushPrimitive(Into.Get(EBlend::Opaque, "cover:"), Corners, 4, Look);
			return true;
		}

		/** For comparisons: XENO_WITHOUT_T7=1 draws as before 13.11's task 7 (no gears, children's models, battle transition, screen wave). */
		static bool WithoutTask7()
		{
			static const bool bWithout = std::getenv("XENO_WITHOUT_T7") != nullptr;
			return bWithout;
		}

		/** The picture of the screen before a battle has a key of its own beside the field's counts of pictures and the world map's. */
		static int BattlePictureKey(uint32 ProgramRuns) { return 0x20000000 | static_cast<int>(ProgramRuns & 0xFFFFFF); }
		/** The window's size the last picture of the screen was taken at: its game screen is scaled to the height, centred across. */
		int PictureWidth = 0, PictureHeight = 0;

		/**
		 * A battle's opening transition (FBattleRuntime::DefaultTransition / SetupTransition), as Weltall's display draws it
		 * (Source/Weltall/Private/Rendering/BattleTransitionRendering.cpp, Screens/BattleView.cpp): the screen cleared to the
		 * transition's background, then its triangles, far entries first and within an entry the last linked first, each
		 * corner where the transitions' own projection puts it (centre 160, 112, distance 512) and showing the pixel of the
		 * picture of the screen before the battle it names, shaded by its colour (128 leaves it as it is). The default
		 * transition's shards are opaque; a setup's mesh adds (kind 1, 4) or averages (2, 3) over black. Triangles past the
		 * screen's sides are the wings Weltall makes for a wide display. False when there is no transition or no picture.
		 */
		bool PushBattleTransition(FCollector& Into, const FBattleGameProgram& Fight)
		{
			const FBattleRuntime& Runtime = Fight.Runtime();
			const FBattleDefaultTransition* Shatter = Runtime.DefaultTransition();
			const FBattleScreenMesh* Mesh = Runtime.SetupTransition();
			if (Shatter == nullptr && Mesh == nullptr)
			{
				return false;
			}
			struct FDrawn
			{
				std::array<std::array<float, 2>, 3> Corners{};
				std::array<std::array<int32, 2>, 3> Pixels{};
				std::array<uint8, 3> Shades{};
				int32 Entry = -1;
			};
			std::vector<FDrawn> Triangles;
			const auto Project = [](const FGteMatrix& Matrix, const FGteVector& Corner, std::array<float, 2>& Screen)
			{
				const std::array<float, 3> View = ViewPoint(Matrix, Corner);
				const float Scale = static_cast<float>(FBattleShatter::ProjectionDistance) / std::max(View[2], 1.0f);
				Screen = {View[0] * Scale + FBattleShatter::ScreenCentreX, View[1] * Scale + FBattleShatter::ScreenCentreY};
				return View[2] >= 1.0f;
			};
			uint8 Background = 0;
			EBlend Blend = EBlend::Opaque;
			if (Shatter != nullptr)
			{
				const std::size_t Buffer = static_cast<std::size_t>(Shatter->Buffer());
				for (int32 Side = 0; Side < FBattleShatter::Sides; ++Side)
				{
					for (int32 Row = 0; Row < FBattleShatter::Rows; ++Row)
					{
						for (int32 Column = FBattleShatterWings::FirstColumn; Column < FBattleShatterWings::EndColumn; ++Column)
						{
							const bool bWing = Column < 0 || Column >= FBattleShatter::Columns;
							const FBattleScreenShard& Shard = bWing ? Shatter->Wings().Shard(Side, Row, Column) : Shatter->Shatter().Shard(Side, Row, Column);
							FDrawn& Drawn = Triangles.emplace_back();
							Drawn.Pixels = FBattleShatter::PicturePixels(Side, Row, Column);
							const FGteMatrix Matrix = FBattleShatter::DrawMatrix(Shard);
							bool bOnScreen = Shard.Position[2] > FBattleShatter::NearestDrawn;
							for (std::size_t Corner = 0; Corner < 3; ++Corner)
							{
								bOnScreen &= Project(Matrix, FBattleShatter::Corners[static_cast<std::size_t>(Side)][Corner], Drawn.Corners[Corner]);
								Drawn.Shades[Corner] = Shard.Colors[Buffer][0];
							}
							Drawn.Entry = bOnScreen ? FBattleShatter::DrawEntry(Shard, Side) : -1;
						}
					}
				}
				Background = Shatter->Backgrounds()[Buffer][0];
			}
			else
			{
				std::vector<FBattleMeshTriangle> Made;
				Mesh->Draw(Runtime.TransitionBuffer(), -Mesh->WingColumns(), Mesh->Columns() + Mesh->WingColumns(), Made);
				for (const FBattleMeshTriangle& Triangle : Made)
				{
					FDrawn& Drawn = Triangles.emplace_back();
					const FBattleMeshLink Link = Mesh->Link(Triangle);
					bool bOnScreen = Link.bLinked;
					for (std::size_t Corner = 0; Corner < 3; ++Corner)
					{
						bOnScreen &= Project(Triangle.Matrix, Triangle.Corners[Corner], Drawn.Corners[Corner]);
						Drawn.Pixels[Corner] = Triangle.Pixels[Corner];
						Drawn.Shades[Corner] = Triangle.Colors[Corner];
					}
					Drawn.Entry = bOnScreen ? Link.Entry : -1;
				}
				Blend = Mesh->Blend() == EBlendMode::Add ? EBlend::Add : EBlend::Average;
			}
			// The screen cleared to the background, across the whole display.
			{
				FLook Look;
				Look.Spans = 1.0f;
				Look.Depth = 3.0f;
				std::array<FCorner, 4> Corners{};
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					Corners[Corner].Pos = {(Corner & 1) != 0 ? static_cast<float>(MenuScreenSize.Width) : 0.0f,
						(Corner & 2) != 0 ? static_cast<float>(MenuScreenSize.Height) : 0.0f, 0.0f};
					Corners[Corner].Color = {Background, Background, Background};
				}
				Mix(Background);
				++ScreenPrimitives;
				PushPrimitive(Into.Get(EBlend::Opaque, {}), Corners, 4, Look);
			}
			if (ScreenPictures.count(BattleScreenBefore) == 0 || PictureWidth <= 0 || PictureHeight <= 0)
			{
				return true;
			}
			// The far entries first; within an entry, the triangle linked last.
			std::vector<std::size_t> Order;
			for (std::size_t Index = Triangles.size(); Index-- > 0;)
			{
				if (Triangles[Index].Entry >= 0)
				{
					Order.push_back(Index);
				}
			}
			std::stable_sort(Order.begin(), Order.end(), [&Triangles](std::size_t A, std::size_t B) { return Triangles[A].Entry > Triangles[B].Entry; });
			// The picture is the window as shown: the game screen scaled to its height and centred across.
			const float Scale = static_cast<float>(PictureHeight) / MenuScreenSize.Height;
			FLook Look;
			Look.Flags = Blend != EBlend::Opaque ? FlagSemi : 0.0f;
			FMeshBuffers& Out = Into.Get(Blend, "cover:");
			for (const std::size_t Index : Order)
			{
				const FDrawn& Drawn = Triangles[Index];
				std::array<FCorner, 4> Corners{};
				for (std::size_t Corner = 0; Corner < 3; ++Corner)
				{
					Corners[Corner].Pos = {Drawn.Corners[Corner][0], Drawn.Corners[Corner][1], 0.0f};
					Corners[Corner].Color = {Drawn.Shades[Corner], Drawn.Shades[Corner], Drawn.Shades[Corner]};
					Corners[Corner].U = (PictureWidth * 0.5f + (static_cast<float>(Drawn.Pixels[Corner][0]) - MenuScreenSize.Width * 0.5f) * Scale) / PictureWidth;
					Corners[Corner].V = static_cast<float>(Drawn.Pixels[Corner][1]) / MenuScreenSize.Height;
				}
				Mix(static_cast<uint32>(Drawn.Corners[0][0] * 16.0f) ^ static_cast<uint32>(Drawn.Corners[0][1] * 16.0f) << 12 ^ Drawn.Shades[0]);
				++ScreenPrimitives;
				PushPrimitive(Out, Corners, 3, Look);
			}
			return true;
		}

		/** The frame's 2D lists: the minimap and the windows in the screen's place, then its fade over the scene's rows. */
		void PushMapLayers(FCollector& Into, const FVram& Vram, const FWorldMapFrame& Frame)
		{
			PushDrawList(Into, Vram, Frame.Minimap);
			PushDrawList(Into, Vram, Frame.Windows);
			bListSpans = true;
			PushDrawList(Into, Vram, Frame.Screen);
			bListSpans = false;
		}
		/** The 2D primitives pushed now are drawn across the display's whole width (the world map's fade over the scene's rows). */
		bool bListSpans = false;
		/** The VRAM rectangles the program's texture animations have written since its run began (palettes and tiles). */
		std::vector<FVramRect> MapAnimated;

		/** After a frame of the world map: the rectangles its animations wrote, gathered. */
		void FollowMapAnimations(const FWorldMapProgram& Map)
		{
			for (const FVramImage& Upload : Map.Drawing().AnimatedUploads())
			{
				const auto Same = [&Upload](const FVramRect& Rect) {
					return Rect.X == Upload.Rect.X && Rect.Y == Upload.Rect.Y && Rect.Width == Upload.Rect.Width && Rect.Height == Upload.Rect.Height;
				};
				if (std::none_of(MapAnimated.begin(), MapAnimated.end(), Same))
				{
					MapAnimated.push_back(Upload.Rect);
				}
			}
		}

		// ---- The Battling program (the gear arena). Its frame is in the world map's form (Battling/BattlingDrawing.h: "the
		// same renderer draws both"), drawn as Weltall's own view of it draws it (MIT): Source/Weltall/Private/Screens/
		// BattlingView.cpp, Capture: the scene through the world map's frame drawing (Rendering/WorldMapFrameDraw.cpp) on
		// the arena's 218 lines, its columns scaled by 320 / the frame's columns, over the frame's clear colour as the GPU
		// fills it; the 2D layer through FMenuDrawBuilder on a screen of the frame's columns by 218 lines, fitted in the
		// display's middle as the world map's; a paused frame's 2D layer over the picture the pause captured. ----

		static constexpr FScreenSize BattlingScreen{static_cast<int16>(FBattlingFrame::ScreenWidth), static_cast<int16>(FBattlingFrame::ScreenHeight)};
		FMenuDrawBuilder ArenaBuilder;
		FMenuFrame ArenaFrame;
		FDrawList ArenaList;
		/** The 2D primitives pushed now are of a screen whose columns are this many of the display's (the winner screen's 640: 1/2). */
		float ListColumnScale = 1.0f;

		const FBattlingGameProgram* Battling() const { return Loop ? Loop->Battling() : nullptr; }

		/** The frame whose scene shows: a paused frame's picture (the frame on the screen as the pause opened), else the latest. */
		const FBattlingFrame* ArenaSceneFrame() const
		{
			const FBattlingGameProgram* Arena = Battling();
			const FBattlingFrame* Latest = Arena != nullptr ? Arena->LatestFrame() : nullptr;
			if (Latest != nullptr && Latest->PictureBlurs > 0 && Arena->PausedPicture() != nullptr)
			{
				return Arena->PausedPicture();
			}
			return Latest;
		}

		/** The display's columns over a frame's: the winner screen's 640 span the bout's 320. */
		static float ArenaColumnScale(const FBattlingFrame& Frame)
		{
			return static_cast<float>(FBattlingFrame::ScreenWidth) / static_cast<float>(std::max<int32>(Frame.Columns, 1));
		}

		/** A frame's 2D layer (FBattlingFrame::Screen) as the view builds it: FMenuDrawBuilder on its own screen, without the player's button pictures. */
		void PushArenaLayer(FCollector& Into, const FVram& Vram, const FBattlingFrame& Frame)
		{
			ArenaFrame.Primitives.assign(Frame.Screen.begin(), Frame.Screen.end());
			ArenaFrame.TextButtons.assign(Frame.TextButtons.begin(), Frame.TextButtons.end());
			ArenaFrame.Number = Frame.Pass + 1;
			ArenaBuilder.Screen = {static_cast<int16>(Frame.Columns), BattlingScreen.Height};
			ArenaBuilder.Build(ArenaFrame, nullptr, 1.0f, ArenaList);
			ListColumnScale = ArenaColumnScale(Frame);
			PushDrawList(Into, Vram, ArenaList);
			ListColumnScale = 1.0f;
		}

		// ---- Pictures the display loads before they are drawn (lazy HD loading) ----

		bool bLazy = false;
		std::unordered_set<std::string> Ready;
		std::set<std::string> Wanted;
		/** Primitives the last builds drew from VRAM while their picture was loading. */
		int Waiting = 0;

		/** Whether a picture (a pack file's path, a "page:" key) may be drawn now; one that may not is asked for. */
		bool IsReady(const std::string& Key)
		{
			if (!bLazy || Ready.count(Key) != 0)
			{
				return true;
			}
			Wanted.insert(Key);
			return false;
		}

		void ForgetReadyPages()
		{
			for (auto Entry = Ready.begin(); Entry != Ready.end();)
			{
				Entry = Entry->rfind("page:", 0) == 0 ? Ready.erase(Entry) : std::next(Entry);
			}
			for (auto Entry = Wanted.begin(); Entry != Wanted.end();)
			{
				Entry = Entry->rfind("page:", 0) == 0 ? Wanted.erase(Entry) : std::next(Entry);
			}
			// A "page:" picture is the scene's: its texels' kinds go with it.
			std::erase_if(KindsOf, [](const auto& Entry) { return Entry.first.rfind("page:", 0) == 0; });
		}

		// ---- The screens beside the field's and the battle's: the menus, the movies, the kernel's notice, the field's picture
		// of the screen, a chapter's card. Which one shows follows Weltall's game screen (Source/Weltall/Private/Screens/
		// GameLoopScreen.cpp, CaptureProgramFrame); each is drawn from the core's frame as its view there draws it:
		// MenuView.cpp (the menu's list through FMenuDrawBuilder over the field's last picture), MovieScreen.h and
		// MoviePictureView.cpp / Rendering/MovieRendering.cpp (the movie's picture, a pixel a screen pixel, at its place),
		// FieldView.cpp and FieldScreenFrame.cpp (the field's movies, its picture of the screen, the screen's pixels in
		// VRAM), ChapterCardView.cpp. (MIT) ----

		FMenuFrame MenuFrame;
		FMenuDrawBuilder MenuBuilder;
		FDrawList MenuList;
		FDrawList NoticeList;
		FChapterCardDrawing CardDrawing;
		FDrawList CardList;
		/** The last BuildScreen drew a chapter's card: the overlay VRAM is its pictures. */
		bool bCardDrawn = false;
		/** The movie picture on screen (the Movie program's or the field's), kept as the display keeps it; a count of pictures followed. */
		std::shared_ptr<const FMdecPicture> MovieShown;
		uint32 MoviePictureSeen = 0;
		int MovieRevision = 0;
		/** The field's movie last followed showed full screen (alone, or with the message windows over it). */
		bool bMovieOverScene = false, bMovieOverField = false;
		const FMoviePlayer* MoviePlayerSeen = nullptr;
		/**
		 * Which movie the picture shown is of, as the core names it (the disc's number and the movie's number in its movie
		 * group, FindMovie: the Movie program's request, Kernel().Movie.Number; the field's, FFieldMovieRequest::Movie), and
		 * the frame number its data gives that picture: what a replacement of the movie is keyed and timed by.
		 */
		int MovieDisc = 0, MovieNumber = -1;
		uint32 MovieShownFrame = 0;
		/** The display's pictures of the screen by the field's count of pictures taken: the game screen's 320 x 224 pixels as 15-bit units. */
		std::unordered_map<int, std::vector<uint16>> ScreenPictures;
		std::vector<uint16> PatchedVram;
		uint64 PatchedStamp = 0;
		/** The 2D layer the last BuildScreen made: its primitives and their FNV-1a hash. */
		int ScreenPrimitives = 0;
		uint32 ScreenHash = 2166136261u;

		void ResetScreens()
		{
			MovieShown.reset();
			MoviePictureSeen = 0;
			MoviePlayerSeen = nullptr;
			bMovieOverScene = bMovieOverField = false;
			MovieDisc = 0;
			MovieNumber = -1;
			MovieShownFrame = 0;
		}

		void Mix(uint32 Value)
		{
			for (int Byte = 0; Byte < 4; ++Byte)
			{
				ScreenHash = (ScreenHash ^ (Value >> (Byte * 8) & 0xFF)) * 16777619u;
			}
		}

		void MixScreen(const FDrawPrimitive& Primitive)
		{
			++ScreenPrimitives;
			Mix(Primitive.CornerCount | static_cast<uint32>(Primitive.Blend) << 8 | (Primitive.Texture ? 1u << 16 : 0u));
			for (std::size_t Corner = 0; Corner < Primitive.CornerCount; ++Corner)
			{
				const FDrawVertex& At = Primitive.Corners[Corner];
				Mix(static_cast<uint32>(static_cast<int32>(At.X * 16.0f)) ^ static_cast<uint32>(static_cast<int32>(At.Y * 16.0f)) << 16);
				Mix(static_cast<uint32>(At.U) | static_cast<uint32>(At.V) << 8 | static_cast<uint32>(At.Color.R) << 16 | static_cast<uint32>(At.Color.G) << 24);
			}
		}

		const FMenuProgram* RunningMenu() const
		{
			const FMenuGameMenus* Shown = bObserved ? ObservedMenus : Menus.get();
			return Shown != nullptr && Loop ? Shown->Running() : nullptr;
		}

		/** The movie playing now and its field's view of it (-1: the Movie program's own). */
		const FMoviePlayer* PlayingMovie(int& View) const
		{
			View = -1;
			if (!Loop)
			{
				return nullptr;
			}
			if (const FMovieProgram* Program = Loop->Movie())
			{
				return Program->Player();
			}
			if (const FFieldProgram* Running = Field(); Running != nullptr && Running->Movie() != nullptr)
			{
				View = static_cast<int>(Running->Movie()->View());
				return &Running->Movie()->Player();
			}
			return nullptr;
		}

		/** After each frame of the game: the movie's picture the display shows, as FMoviePictureView and FFieldView follow it. */
		/** What follows each frame of the game: the world map's culling and animations, the screens shown. */
		void AfterFrame();

		void FollowScreens()
		{
			if (!Loop)
			{
				return;
			}
			int View = -1;
			const FMoviePlayer* Player = PlayingMovie(View);
			const FFieldProgram* Running = Field();
			// The field's movie frame it ended in still shows its last picture (FieldView.cpp, Follow).
			if (Player == nullptr && Running != nullptr && Running->Runtime().LastFrame() == EFieldFrame::Movie && MovieShown && bMovieOverScene)
			{
				return;
			}
			if (Player != MoviePlayerSeen)
			{
				ResetScreens();
				MoviePlayerSeen = Player;
				if (Player != nullptr)
				{
					MovieDisc = Session->DiscNumber() + 1;
					MovieNumber = Loop->Movie() != nullptr ? static_cast<int>(Session->Kernel().Movie.Number) : static_cast<int>(Running->Movie()->Request().Movie);
				}
			}
			if (Player == nullptr)
			{
				return;
			}
			bMovieOverScene = View != static_cast<int>(EFieldMovieView::InScene);
			bMovieOverField = View == static_cast<int>(EFieldMovieView::OverField);
			if (Player->Picture() && (Player->PictureNumber() != MoviePictureSeen || Player->Picture() != MovieShown))
			{
				MovieShown = Player->Picture();
				MoviePictureSeen = Player->PictureNumber();
				MovieShownFrame = Player->FrameNumber();
				++MovieRevision;
			}
		}

		/** What the display shows now (GameLoopScreen.cpp, CaptureProgramFrame). */
		EScreenKind ScreenNow() const
		{
			if (!Loop)
			{
				return EScreenKind::Blank;
			}
			if (Loop->Stage() == EGameLoopStage::Boot)
			{
				return Loop->Notice() != nullptr ? EScreenKind::Notice : EScreenKind::Blank;
			}
			if (Loop->Movie() != nullptr)
			{
				return EScreenKind::Movie;
			}
			if (Field() != nullptr)
			{
				if (RunningMenu() != nullptr)
				{
					return EScreenKind::Menu;
				}
				return MovieShown && bMovieOverScene ? EScreenKind::FieldMovie : EScreenKind::Field;
			}
			if (WorldMap() != nullptr)
			{
				return RunningMenu() != nullptr ? EScreenKind::Menu : EScreenKind::WorldMap;
			}
			if (Battle() != nullptr)
			{
				return EScreenKind::Battle;
			}
			if (Battling() != nullptr)
			{
				return EScreenKind::Battling;
			}
			return EScreenKind::Blank;
		}

		/** The screen the 2D layer is laid on: the Movie program's and the notice's are 320 x 240, the world map's 320 x 216, the arena's 320 x 218, the others' 320 x 224. */
		static FScreenSize ScreenSizeOf(EScreenKind Kind)
		{
			return Kind == EScreenKind::Notice ? FBootNotice::ScreenSize : Kind == EScreenKind::Movie ? FScreenSize{320, 240}
				: Kind == EScreenKind::WorldMap ? WorldMapScreen : Kind == EScreenKind::Battling ? BattlingScreen : MenuScreenSize;
		}

		/**
		 * The movie's picture, a pixel a screen pixel from the top left of its place (Placement), as much of it as the
		 * place holds (Rendering/MovieRendering.cpp's ScreenMovie: the Movie program's window shows its top 216 lines 10
		 * lines down a 320 x 240 screen; the field's fills its 320 x 224 screen).
		 */
		void PushMovie(FCollector& Into, const FScreenRect& Placement)
		{
			if (!MovieShown || MovieShown->Width <= 0 || MovieShown->Height <= 0)
			{
				return;
			}
			const float Wide = static_cast<float>(std::min<int32>(MovieShown->Width, Placement.Width));
			const float High = static_cast<float>(std::min<int32>(MovieShown->Height, Placement.Height));
			FLook Look;
			Look.Flags = FlagRaw;
			std::array<FCorner, 4> Corners{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				const bool bRight = (Corner & 1) != 0, bLower = (Corner & 2) != 0;
				Corners[Corner].Pos = {Placement.X + (bRight ? Wide : 0.0f), Placement.Y + (bLower ? High : 0.0f), 0.0f};
				Corners[Corner].U = bRight ? Wide / static_cast<float>(MovieShown->Width) : 0.0f;
				Corners[Corner].V = bLower ? High / static_cast<float>(MovieShown->Height) : 0.0f;
			}
			Mix(static_cast<uint32>(MovieRevision));
			++ScreenPrimitives;
			PushPrimitive(Into.Get(EBlend::Opaque, "movie:"), Corners, 4, Look);
		}

		/**
		 * The field's picture of the screen (FFieldFrameCover, FieldScreenFrame.cpp): the frame shown last when it was
		 * taken, over the whole display, scaled about its centre (4.12), its texels at the cover's brightness; added to
		 * what lies below, or opaque with its black pixels letting it through. Drawn once the display has given the picture.
		 */
		void PushCover(FCollector& Into, const FFieldFrameCover& Cover)
		{
			if (!Cover.bShown || !Cover.bScreen || ScreenPictures.count(Cover.Taken) == 0)
			{
				return;
			}
			const float Scale = static_cast<float>(Cover.Scale) / static_cast<float>(FFieldCover::UnitScale);
			FLook Look;
			Look.Spans = 1.0f;
			Look.Flags = Cover.bAdditive ? FlagSemi : 0.0f;
			const float Half[2] = {MenuScreenSize.Width * 0.5f, MenuScreenSize.Height * 0.5f};
			std::array<FCorner, 4> Corners{};
			for (std::size_t Corner = 0; Corner < 4; ++Corner)
			{
				const float Sx = (Corner & 1) != 0 ? 1.0f : -1.0f, Sy = (Corner & 2) != 0 ? 1.0f : -1.0f;
				Corners[Corner].Pos = {Half[0] + Sx * Half[0] * Scale, Half[1] + Sy * Half[1] * Scale, 0.0f};
				Corners[Corner].Color = {Cover.Brightness, Cover.Brightness, Cover.Brightness};
				Corners[Corner].U = (Corner & 1) != 0 ? 1.0f : 0.0f;
				Corners[Corner].V = (Corner & 2) != 0 ? 1.0f : 0.0f;
			}
			Mix(static_cast<uint32>(Cover.Taken) ^ static_cast<uint32>(Cover.Scale) << 8 ^ Cover.Brightness);
			++ScreenPrimitives;
			PushPrimitive(Into.Get(Cover.bAdditive ? EBlend::Add : EBlend::Opaque, "cover:"), Corners, 4, Look);
		}

		/** The field's frame's 2D layer with its picture of the screen at its place among the primitives, less the primitives of SkippedKey. */
		void PushFieldLayer(FCollector& Into, const FVram& Vram, const FFieldFrame& Frame, std::size_t First, uint32 SkippedKey)
		{
			const std::size_t At = std::max<std::size_t>(First, Frame.Cover.LayerIndex);
			PushDrawList(Into, Vram, Frame.Screen, First, At, SkippedKey);
			PushCover(Into, Frame.Cover);
			PushDrawList(Into, Vram, Frame.Screen, At, SIZE_MAX, SkippedKey);
		}

		/** A chapter's card over the field (ChapterCardView.cpp), from its own pictures (the overlay VRAM). */
		void PushChapterCard(FCollector& Into)
		{
			bCardDrawn = false;
			if (!Session)
			{
				return;
			}
			const std::string Line = Session->ChapterCardLine();
			if (Line.empty() || Session->ChapterCard().Level() <= 0)
			{
				return;
			}
			CardDrawing.Build(Line, Session->ChapterCard().Level(), Session->Text().Font, CardList);
			bCardDrawn = true;
			Into.Vram = EVramSource::OverlayVram;
			PushDrawList(Into, CardDrawing.Pictures(), CardList, 0, SIZE_MAX, 0, false);
			Into.Vram = EVramSource::SceneVram;
		}

		/** The menu's list as MenuView.cpp builds it: its frame through FMenuDrawBuilder. */
		void PushMenu(FCollector& Into, const FMenuProgram& Menu)
		{
			const FMenuFrame& Snapshot = Menu.Snapshot();
			if (Snapshot.Number == 0)
			{
				return;
			}
			MenuFrame.Primitives.assign(Snapshot.Primitives.begin(), Snapshot.Primitives.end());
			// The File screen's hint of the save stores its two cards do not show (the port's eight stores), as MenuView.cpp
			// appends it; nothing while the cards are not shown.
			AddStorePairHint(Snapshot.Stores, Menu.Resources().Sheet(), MenuFrame.Primitives);
			MenuFrame.Layer = Snapshot.Layer;
			MenuFrame.Gear = Snapshot.Gear;
			MenuFrame.Keys = Snapshot.Keys;
			MenuFrame.TextButtons = Snapshot.TextButtons;
			MenuFrame.Number = Snapshot.Number;
			MenuBuilder.Build(MenuFrame, nullptr, 1.0f, MenuList);
			Into.Vram = EVramSource::ScreenVram;
			PushDrawList(Into, Menu.Vram(), MenuList);
			Into.Vram = EVramSource::SceneVram;
		}

		/** The screen's pixels the field copied into VRAM (FFieldFrame::ScreenInVram), from the display's pictures, into a copy of Vram. */
		/** Counts the display's pictures given (SetScreenPicture). */
		uint32 PicturesGiven = 0;

		/** Which screen pixels the field's VRAM holds now (0: none the display has given): the regions, their pictures. */
		uint64 ScreenInVramStamp(const FFieldFrame& Frame) const
		{
			uint64 Stamp = 0;
			for (const FFieldScreenInVram& Region : Frame.ScreenInVram)
			{
				if (ScreenPictures.count(Region.Taken) != 0)
				{
					Stamp = (Stamp ^ (static_cast<uint64>(static_cast<uint16>(Region.Rect.X)) | static_cast<uint64>(static_cast<uint16>(Region.Rect.Y)) << 16
						| static_cast<uint64>(static_cast<uint16>(Region.Rect.Width)) << 32 | static_cast<uint64>(Region.Taken) << 48 | 1)) * 1099511628211ull;
				}
			}
			return Stamp != 0 ? Stamp ^ PicturesGiven : 0;
		}

		const uint16* PatchScreenInVram(const FVram& Vram, const FFieldFrame& Frame)
		{
			const uint64 Regions = ScreenInVramStamp(Frame);
			if (Regions == 0)
			{
				return Vram.AllUnits().data();
			}
			const uint64 Stamp = (static_cast<uint64>(Vram.Lineage()) << 32 ^ Vram.Revision()) * 1099511628211ull ^ Regions;
			if (Stamp == PatchedStamp && PatchedVram.size() == Vram.AllUnits().size())
			{
				return PatchedVram.data();
			}
			PatchedStamp = Stamp;
			PatchedVram.assign(Vram.AllUnits().begin(), Vram.AllUnits().end());
			for (const FFieldScreenInVram& Region : Frame.ScreenInVram)
			{
				const auto Found = ScreenPictures.find(Region.Taken);
				if (Found == ScreenPictures.end())
				{
					continue;
				}
				for (int32 Row = 0; Row < Region.Rect.Height; ++Row)
				{
					for (int32 Column = 0; Column < Region.Rect.Width; ++Column)
					{
						const int32 X = Region.ScreenX + Column, Y = Region.ScreenY + Row;
						uint16 Unit = 0;
						if (X >= 0 && Y >= 0 && X < MenuScreenSize.Width && Y < MenuScreenSize.Height)
						{
							// The pixels as drawn before the copy: at Brightness, 128 as shown.
							const uint16 Pixel = Found->second[static_cast<std::size_t>(Y * MenuScreenSize.Width + X)];
							const auto Channel = [&](int Shift) { return static_cast<uint16>(std::min(31, (Pixel >> Shift & 31) * Region.Brightness / 128)); };
							Unit = static_cast<uint16>(Channel(0) | Channel(5) << 5 | Channel(10) << 10);
						}
						const int32 UnitX = (Region.Rect.X + Column) & (FVram::Width - 1), UnitY = (Region.Rect.Y + Row) & (FVram::Height - 1);
						PatchedVram[static_cast<std::size_t>(UnitY * FVram::Width + UnitX)] = Unit;
					}
				}
			}
			return PatchedVram.data();
		}
	};

	FSession::FSession() : Impl(std::make_unique<FImpl>()) {}
	FSession::~FSession()
	{
		if (Impl && Impl->bObserved)
		{
			(void)Impl->Loop.release();
			(void)Impl->Session.release();
		}
	}

	std::string FSession::Open(const std::string& GamesFolder, const std::string& TranslationImage)
	{
		FImpl& I = *Impl;
		if (TranslationImage.empty())
		{
			I.Library = FGameLibrary::Scan(std::filesystem::u8path(GamesFolder));
			I.Disc = I.Library.Find(EDiscRelease::UsaDisc1);
			if (I.Disc == nullptr)
			{
				return "USA disc 1 not found in " + GamesFolder;
			}
		}
		else
		{
			// The library keeps only discs Weltall knows: the translation's is opened by itself (as FGameLibrary::Scan opens one).
			auto Image = FCdImage::Open(std::filesystem::u8path(TranslationImage));
			if (!Image)
			{
				return "translation image: " + Image.Error().Message;
			}
			auto Disc = FIso9660::Open(std::move(*Image));
			if (!Disc)
			{
				return "translation image: " + Disc.Error().Message;
			}
			I.TranslationDisc = std::make_unique<FIso9660>(std::move(*Disc));
			I.Disc = I.TranslationDisc.get();
		}
		auto Executable = ReadBootExecutable(*I.Disc);
		if (!Executable)
		{
			return "boot executable unreadable";
		}
		I.Executable = std::make_unique<FPsxExecutable>(std::move(*Executable));
		I.Menus = std::make_unique<FMenuGameMenus>(*I.Executable);
		auto Index = FGameFileIndex::Read(*I.Executable);
		if (!Index)
		{
			return Index.Error().Message;
		}
		I.Index = std::make_unique<FGameFileIndex>(std::move(*Index));
		TResult<FDiscIdentity> Identity = MakeError("no disc");
		if (TranslationImage.empty())
		{
			Identity = IdentifyDisc(*I.Disc);
			I.Language = "en";
		}
		else
		{
			TResult<FTranslation> Translation = RecognizeTranslation(*I.Disc, *I.Executable);
			if (!Translation)
			{
				return Translation.Error().Message;
			}
			Identity = Translation->Identity;
			I.Language = Translation->Language;
			// The widths reach the font as Weltall gives a player's font sheet (Assets/font): through an asset store on the
			// image, which the font's load reads (LoadMesResident: Image.FontSheet()). The store's folder ("assets" beside
			// the image) holds nothing, so every file is the disc's own.
			const std::filesystem::path Assets = std::filesystem::absolute(std::filesystem::u8path(TranslationImage)).parent_path() / "assets";
			auto Store = FDiscAssetStore::Open(Assets, "rus.disc1", I.Disc->Image(), *I.Index);
			if (!Store)
			{
				return "translation's asset store: " + Store.Error().Message;
			}
			I.TranslationAssets = std::move(*Store);
			I.TranslationAssets->SetFontSheet(Translation->Widths);
			I.TranslationAssets->SetEnabled(true);
			I.Disc->Image().SetAssetStore(I.TranslationAssets);
			// The maps the core would refuse (a section longer than its stream), as the console reads them (MendedMapArchives).
			const std::vector<FModFile> Mended = MendedMapArchives(I.Disc->Image(), *I.Index, I.MendedMaps);
			I.Disc->Image().SetModFiles(FDiscModFiles::Make(*I.Index, 1, Mended));
			I.bRussianWindows = true;
			// Under the game's "INSERT DISC 2" while its image is not found, Weltall's English "Not found in Games." would be
			// typed in this font's Latin letters: instead "Диск не найден." in the translation's own codes (its letters
			// 93h-B6h, and the Latin ones it types for look-alike Cyrillic: tools/rus_text.py, RUSSIAN_OWN, LOOKALIKE). The
			// shell's line over the game says where to put the image (main.gd, _follow_disc).
			// Д 95h, и 'u' 51h, с 'c' 3Fh, к 'k' 47h, space 10h, н ACh, е 'e' 41h, а 'a' 3Dh, й A9h, д 'g' 43h, '.' 14h.
			I.Menus->SetDiscNotFoundText({0x95, 0x51, 0x3F, 0x47, 0x10, 0xAC, 0x41, 0x10, 0xAC, 0x3D, 0xA9, 0x43, 0x41, 0xAC, 0x14, 0x00});
		}
		if (!Identity)
		{
			return Identity.Error().Message;
		}
		// The game's sound starts from the disc played. FGameSoundSession::Start(Disc) knows only the discs IdentifyDisc
		// knows; a translation's starts as the identity the bridge recognized it as (Start(Disc, Vouched), xeno-local),
		// its sound files being USA disc 1's byte for byte (the Russian's: banks 1/2-5, effects 4/168, music directory 28,
		// the song table in 1/14 at 3E4DCh; tools/rus_files.py). XENO_USA_SOUND=1: from USA disc 1 in the games folder
		// instead, as before (for comparisons: the same samples).
		I.SoundDisc = I.Disc;
		I.SoundVouched.reset();
		if (!TranslationImage.empty())
		{
			if (const char* UsaSound = std::getenv("XENO_USA_SOUND"); UsaSound != nullptr && std::string(UsaSound) == "1")
			{
				I.Library = FGameLibrary::Scan(std::filesystem::u8path(GamesFolder));
				I.SoundDisc = I.Library.Find(EDiscRelease::UsaDisc1);
				if (I.SoundDisc == nullptr)
				{
					return "USA disc 1 (the translation's sound) not found in " + GamesFolder;
				}
			}
			else
			{
				I.SoundVouched = *Identity;
			}
		}
		auto Sound = I.StartSound();
		if (!Sound)
		{
			return Sound.Error().Message;
		}
		I.Sound = std::move(*Sound);
		I.Unheard = std::make_unique<FUnheardGameSound>(*I.Sound->Sound());
		I.Identity = *Identity;
		I.DiscId = !TranslationImage.empty() ? std::string("rus.disc1") : std::string(DiscReleaseId(Identity->Release)) + (Identity->bPatched ? ".patched" : "");
		// Where the drive looks for the other disc (FImpl::SeekDisc); the translation's recognized disc is its first.
		I.PlayedNumber = !TranslationImage.empty() ? 0 : DiscNumberOfRelease(Identity->Release) - 1;
		I.GamesFolder = GamesFolder;
		I.TranslationImage = TranslationImage;
		return I.PowerOn();
	}

	std::string FSession::Restart()
	{
		FImpl& I = *Impl;
		if (!I.Session || !I.Identity)
		{
			return "not open";
		}
		// The loop and the session read the old game; the scenery caches hold the old VRAM's regions, and a new runtime
		// counts its map loads from the start again, so the map-load check alone would not see the change.
		I.Loop.reset();
		I.Session.reset();
		I.ForgetScenery();
		I.FrameHits.clear();
		I.SceneKey = -1;
		// A sweep judges each map by itself: no picture known from palettes seen on the maps before.
		I.SamePalettePictures.clear();
		return I.PowerOn();
	}

	const std::string& FSession::Language() const
	{
		return Impl->Language;
	}

	std::vector<FSession::FOpenMessage> FSession::OpenMessages() const
	{
		const FImpl& I = *Impl;
		std::vector<FOpenMessage> Open;
		const FFieldProgram* Field = I.Field();
		if (Field == nullptr)
		{
			return Open;
		}
		const FEventContext& Context = Field->Runtime().Context();
		const std::vector<uint8>& Table = Field->Runtime().Map().Messages;
		const TResult<FMessageTable> Parsed = FMessageTable::Parse(Table);
		std::vector<const FFieldMessageWindow*> Windows;
		for (const FFieldMessageWindow& Window : Context.Messages.Windows)
		{
			if (Window.bOpen)
			{
				Windows.push_back(&Window);
			}
		}
		std::sort(Windows.begin(), Windows.end(), [](const FFieldMessageWindow* A, const FFieldMessageWindow* B) { return A->Age < B->Age; });
		for (const FFieldMessageWindow* Window : Windows)
		{
			FOpenMessage Message;
			Message.Map = Context.RunningMap;
			// The frame is the lines' height and 16 pixels more (FieldMessageOpen.cpp, InitWindow).
			Message.Lines = (Window->Rect.Height - 16) / 14;
			Message.bPortrait = Window->bPortrait;
			const std::size_t Size = MesMessageSize(Window->Message);
			Message.Codes.assign(Window->Message.begin(), Window->Message.begin() + static_cast<std::ptrdiff_t>(Size));
			// Its number: the table's message that starts where the window's does.
			for (int32 Index = 0; Parsed && Index < Parsed->Count(); ++Index)
			{
				if (Parsed->String(Index).data() == Window->Message.data())
				{
					Message.Index = Index;
					break;
				}
			}
			Open.push_back(std::move(Message));
		}
		return Open;
	}

	bool FSession::HoldsFieldMap(int Number) const
	{
		const FImpl& I = *Impl;
		return I.Disc != nullptr && I.Index && Weltall::HoldsFieldMap(I.Disc->Image(), *I.Index, Number);
	}

	std::vector<std::string> FSession::TakeMissingNames()
	{
		std::vector<std::string> Names(Impl->MissingNames.begin(), Impl->MissingNames.end());
		Impl->MissingNames.clear();
		return Names;
	}

	FSpritePieceVerdict FSession::ClassifySpriteQuad(const FVram& Vram, const FSpriteQuad& Quad)
	{
		FImpl& I = *Impl;
		// The caller's VRAM changes between calls: nothing worked out over the last one holds (the agreeing palettes' pictures do).
		I.FrameHits.clear();
		I.UsedIndices.clear();
		I.PageStates.clear();
		I.MissingNames.clear();
		const int Hd = I.SpriteHd, Partial = I.SpritePartial, Pieces = I.SpritePieces;
		std::vector<FSurface> Out;
		FCollector Into(Out, true);
		// As BuildWorld pushes a field sprite's piece.
		const std::array<std::array<int16, 2>, 4> Texels{{{Quad.U0, Quad.V0}, {Quad.U1, Quad.V0}, {Quad.U0, Quad.V1}, {Quad.U1, Quad.V1}}};
		std::array<std::array<float, 3>, 4> Places{};
		for (std::size_t Corner = 0; Corner < 4; ++Corner)
		{
			Places[Corner] = ToGodot(ViewPoint(Quad.Matrix, Quad.Corners[Corner]));
		}
		I.PushViewQuadAt(Into, Vram, Places, Texels, Quad.TexturePage, Quad.Clut, true, Quad.ColorCode & 0xFFFFFF, (Quad.ColorCode >> 24 & 1) != 0,
			(Quad.ColorCode >> 25 & 1) != 0, true, true);
		FSpritePieceVerdict Verdict;
		Verdict.Kind = I.SpriteHd > Hd ? 0 : I.SpritePartial > Partial ? 1 : 2;
		if (I.SpritePieces == Pieces)
		{
			Verdict.Kind = -1; // not looked up at all (no pack, or texels outside the page)
		}
		// The texels the lookup took: from the first to the last (PushViewQuadAt's sprite rule).
		const FTexturePage Page = FTexturePage::FromPortAttribute(Quad.TexturePage);
		const FClutPosition Clut = FClutPosition::FromPortAttribute(Quad.Clut);
		const int Columns = Quad.U1 - Quad.U0, Rows = Quad.V1 - Quad.V0;
		const int LastU = std::max(Quad.U0, Quad.U1) - (Columns != 0 ? 1 : 0), LastV = std::max(Quad.V0, Quad.V1) - (Rows != 0 ? 1 : 0);
		const int FirstU = std::min<int>(Quad.U0, Quad.U1), FirstV = std::min<int>(Quad.V0, Quad.V1);
		Verdict.PageX = Page.X;
		Verdict.PageY = Page.Y;
		Verdict.Depth = static_cast<int>(Page.Depth);
		Verdict.ClutX = Clut.X;
		Verdict.ClutY = Clut.Y;
		Verdict.U = FirstU;
		Verdict.V = FirstV;
		Verdict.Width = std::max(1, LastU - FirstU + 1);
		Verdict.Height = std::max(1, LastV - FirstV + 1);
		Verdict.Texels = Verdict.Width * Verdict.Height;
		// Each stretch drawn: its corners 0 and 3 (PushPrimitive's triangles 0 1 2 and 1 3 2) in the piece's quad.
		const auto Along = [&](const float* Pos, std::size_t Edge)
		{
			float Dot = 0.0f, Length = 0.0f;
			for (std::size_t Axis = 0; Axis < 3; ++Axis)
			{
				const float E = Places[Edge][Axis] - Places[0][Axis];
				Dot += (Pos[Axis] - Places[0][Axis]) * E;
				Length += E * E;
			}
			return Length > 0.0f ? Dot / Length : 0.0f;
		};
		for (const FSurface& Surface : Out)
		{
			const FMeshBuffers& Mesh = Surface.Mesh;
			for (std::size_t First = 0; First + 6 <= Mesh.Vertices(); First += 6)
			{
				FSpritePieceDraw Draw;
				Draw.Texture = Surface.Texture;
				const float* P0 = &Mesh.Pos[First * 3];
				const float* P3 = &Mesh.Pos[(First + 4) * 3];
				Draw.Cell = {Along(P0, 1), Along(P0, 2), Along(P3, 1), Along(P3, 2)};
				Draw.Source = {Mesh.Uv[First * 2], Mesh.Uv[First * 2 + 1], Mesh.Uv[(First + 4) * 2], Mesh.Uv[(First + 4) * 2 + 1]};
				if (Draw.Texture.empty())
				{
					Verdict.TexelsFromVram += std::fabs(Draw.Cell[2] - Draw.Cell[0]) * std::fabs(Draw.Cell[3] - Draw.Cell[1]) * Verdict.Texels;
				}
				Verdict.Draws.push_back(std::move(Draw));
			}
		}
		// What the lookup tried: the uploads under the texels (their own names, the reduced palette's, a palette agreeing
		// on their colours), the other palettes the pack has each under, the drawn rectangle's name.
		if (I.PackByUpload.empty())
		{
			for (const auto& [Key, Kind] : I.Pack)
			{
				I.PackByUpload[static_cast<uint32>(Key >> 32)].push_back(static_cast<uint32>(Key));
			}
		}
		const uint32 View = PackTextureView(Page, Clut);
		const std::vector<FBeetleTexturePart> Parts = I.PartsUnder(Vram, Page, Clut, FirstU, FirstV, Verdict.Width, Verdict.Height);
		bool bAllHave = !Parts.empty(), bOtherPalettes = false;
		for (const FBeetleTexturePart& Part : Parts)
		{
			Verdict.Names.push_back({Part.Upload, Part.Palette});
			const bool bOwn = I.InPack(PackKey(Part.Upload, Part.Palette)) != nullptr;
			const bool bReduced = I.InPack(PackKey(Part.Upload, Part.ReducedPalette)) != nullptr;
			const uint64 Through = I.PictureName(Vram, View, Part, true);
			const bool bCovers = Part.U == 0 && Part.V == 0 && Part.Width >= Verdict.Width && Part.Height >= Verdict.Height;
			char Line[256];
			std::snprintf(Line, sizeof(Line), "%s[%s at %d,%d %dx%d of %dx%d units%s: own %d reduced %x:%d through %s", Verdict.Tried.empty() ? "" : " ",
				BeetleTextureFileName({Part.Upload, Part.Palette}).c_str(), Part.U, Part.V, Part.Width, Part.Height, Part.UploadUnitsWide, Part.UploadUnitsHigh,
				bCovers ? ", covers" : "", bOwn ? 1 : 0, Part.ReducedPalette, bReduced ? 1 : 0,
				Through != 0 && !bOwn && !bReduced ? BeetleTextureFileName({static_cast<uint32>(Through >> 32), static_cast<uint32>(Through)}).c_str() : "-");
			Verdict.Tried += Line;
			std::string Others;
			const auto Found = I.PackByUpload.find(Part.Upload);
			if (Found != I.PackByUpload.end())
			{
				for (const uint32 Palette : Found->second)
				{
					if (Palette != Part.Palette && Palette != Part.ReducedPalette)
					{
						char Name[16];
						std::snprintf(Name, sizeof(Name), "%s%x", Others.empty() ? "" : "/", Palette);
						Others += Name;
					}
				}
			}
			Verdict.Tried += " others " + (Others.empty() ? std::string("-") : Others) + "]";
			const bool bHas = bOwn || bReduced || Through != 0;
			bAllHave = bAllHave && bHas;
			bOtherPalettes = bOtherPalettes || (!bHas && !Others.empty());
		}
		bool bRect = false;
		if (Page.Depth == ETextureDepth::Indexed4)
		{
			const uint64 Rect = I.RectKey(Vram, Page, Clut, FirstU, FirstV, Verdict.Width, Verdict.Height);
			bRect = Rect != 0 && I.InPack(Rect) != nullptr;
			Verdict.Tried += " rect " + (Rect != 0 ? BeetleTextureFileName({static_cast<uint32>(Rect >> 32), static_cast<uint32>(Rect)}) : std::string("-"))
				+ (bRect ? " in pack" : " absent");
		}
		if (Verdict.Kind > 0)
		{
			Verdict.Miss = Parts.empty() ? "d" : bAllHave || bRect ? "c" : bOtherPalettes ? "b" : "a";
		}
		return Verdict;
	}

	std::string FSession::DebugActorPieces(int Actor)
	{
		FImpl& I = *Impl;
		const FFieldFrame* Frame = I.Field() != nullptr ? I.Frame() : nullptr;
		if (Frame == nullptr)
		{
			return {};
		}
		const FVram& Vram = I.Field()->Drawing().Vram();
		std::string Out;
		for (const FFieldCharacterQuad& Character : Frame->Quads)
		{
			if (Character.Character >= Frame->Characters.size() || static_cast<int>(Frame->Characters[Character.Character].BlendKey >> 3) != Actor
				|| Frame->Characters[Character.Character].bOnFloor)
			{
				continue;
			}
			const FSpriteQuad& Quad = Character.Quad;
			const FSpritePieceVerdict Verdict = ClassifySpriteQuad(Vram, Quad);
			const std::array<float, 3> C0 = ViewPoint(FGteMatrix::Identity(), Quad.Corners[0]), C3 = ViewPoint(FGteMatrix::Identity(), Quad.Corners[3]);
			char Head[400];
			std::snprintf(Head, sizeof(Head),
				"{\"actor\":%d,\"x0\":%g,\"y0\":%g,\"x1\":%g,\"y1\":%g,\"u\":%d,\"v\":%d,\"w\":%d,\"h\":%d,\"page\":[%d,%d,%d],\"clut\":[%d,%d],\"kind\":%d,\"miss\":\"%s\",\"texels\":\"",
				Actor, C0[0], C0[1], C3[0], C3[1], Verdict.U, Verdict.V, Verdict.Width, Verdict.Height, Verdict.PageX, Verdict.PageY, Verdict.Depth, Verdict.ClutX,
				Verdict.ClutY, Verdict.Kind, Verdict.Miss.c_str());
			Out += Head;
			// The texels shown, first to last, through the CLUT (alpha 0 for colour 0).
			const int Per = TexelsPerUnit(static_cast<ETextureDepth>(Verdict.Depth));
			for (int V = Verdict.V; V < Verdict.V + Verdict.Height; ++V)
			{
				for (int U = Verdict.U; U < Verdict.U + Verdict.Width; ++U)
				{
					const uint16 Word = Vram.TexelAt(Verdict.PageX + U / Per, Verdict.PageY + V);
					const uint16 Colour = Per == 4 ? Vram.TexelAt(Verdict.ClutX + (Word >> ((U & 3) * 4) & 15), Verdict.ClutY)
						: Per == 2 ? Vram.TexelAt(Verdict.ClutX + (Word >> ((U & 1) * 8) & 255), Verdict.ClutY) : Word;
					char Texel[12];
					std::snprintf(Texel, sizeof(Texel), "%02x%02x%02x%02x", (Colour & 31) * 255 / 31, (Colour >> 5 & 31) * 255 / 31, (Colour >> 10 & 31) * 255 / 31,
						Colour == 0 ? 0 : 255);
					Out += Texel;
				}
			}
			Out += "\",\"draws\":[";
			for (std::size_t Draw = 0; Draw < Verdict.Draws.size(); ++Draw)
			{
				const FSpritePieceDraw& D = Verdict.Draws[Draw];
				std::string Path = D.Texture;
				std::replace(Path.begin(), Path.end(), '\\', '/');
				char Body[160];
				std::snprintf(Body, sizeof(Body), "\",\"cell\":[%g,%g,%g,%g],\"src\":[%g,%g,%g,%g]}", D.Cell[0], D.Cell[1], D.Cell[2], D.Cell[3], D.Source[0],
					D.Source[1], D.Source[2], D.Source[3]);
				Out += std::string(Draw ? "," : "") + "{\"t\":\"" + Path + Body;
			}
			std::string Tried = Verdict.Tried;
			std::replace(Tried.begin(), Tried.end(), '"', '\'');
			Out += "],\"tried\":\"" + Tried + "\"}\n";
		}
		return Out;
	}

	std::string FSession::SetAliasIndex(const std::string& Path)
	{
		FImpl& I = *Impl;
		I.AliasBySize.clear();
		I.AliasFound.clear();
		I.bAliasOn = false;
		if (Path.empty())
		{
			return {};
		}
		std::ifstream File(std::filesystem::u8path(Path), std::ios::binary);
		char Magic[4] = {};
		uint32 Version = 0, Count = 0;
		File.read(Magic, 4);
		File.read(reinterpret_cast<char*>(&Version), 4);
		File.read(reinterpret_cast<char*>(&Count), 4);
		if (!File || std::string(Magic, 4) != "XALI" || Version != 1)
		{
			return "not an alias index: " + Path;
		}
		for (uint32 Entry = 0; Entry < Count; ++Entry)
		{
			uint32 Upload = 0, Palette = 0;
			uint16 Wide = 0, High = 0;
			File.read(reinterpret_cast<char*>(&Upload), 4);
			File.read(reinterpret_cast<char*>(&Palette), 4);
			File.read(reinterpret_cast<char*>(&Wide), 2);
			File.read(reinterpret_cast<char*>(&High), 2);
			FImpl::FAliasEntry Alias;
			Alias.Key = PackKey(Upload, Palette);
			Alias.Texels.resize(static_cast<std::size_t>(Wide) * High);
			File.read(reinterpret_cast<char*>(Alias.Texels.data()), static_cast<std::streamsize>(Alias.Texels.size() * 2));
			if (!File)
			{
				return "alias index cut short: " + Path;
			}
			I.AliasBySize[static_cast<uint32>(Wide) << 16 | High].push_back(std::move(Alias));
		}
		I.bAliasOn = true;
		if (const char* Report = std::getenv("XENO_ALIAS_REPORT"); Report != nullptr && I.AliasReport == nullptr)
		{
			I.AliasReport = std::fopen(Report, "ab");
		}
		return {};
	}

	void FSession::ForgetSamePalettes()
	{
		Impl->SamePalettePictures.clear();
	}

	std::string FSession::TakeSpriteMisses()
	{
		std::string Out;
		for (const auto& [Key, Count] : Impl->SpriteMisses)
		{
			Out += Key.first + "," + Key.second + "," + std::to_string(Count) + "\n";
		}
		Impl->SpriteMisses.clear();
		return Out;
	}

	std::string FSession::TakeSpritePalettes()
	{
		std::string Out;
		for (const auto& [Key, Entry] : Impl->SpritePalettes)
		{
			char Line[96];
			std::snprintf(Line, sizeof(Line), "%x,%x,%d,%d,%d,%lld,", static_cast<uint32>(Key >> 32), static_cast<uint32>(Key), Entry.ClutX, Entry.ClutY,
				Entry.Depth, Entry.Pieces);
			Out += Line + Entry.Colours + "\n";
		}
		Impl->SpritePalettes.clear();
		return Out;
	}

	std::string FSession::SetPack(const std::string& Folder)
	{
		FImpl& I = *Impl;
		I.Pack.clear();
		I.PackByUpload.clear();
		I.AliasFound.clear();
		I.ForgetScenery();
		I.PackFolder = Folder;
		// XENO_ALIAS=<index> (headless tools): pictures found by content for uploads the pack has no name for (SetAliasIndex).
		if (const char* Alias = std::getenv("XENO_ALIAS"); Alias != nullptr && I.AliasBySize.empty())
		{
			if (const std::string Error = SetAliasIndex(Alias); !Error.empty())
			{
				std::fprintf(stderr, "alias: %s\n", Error.c_str());
			}
		}
		std::error_code Error;
		for (std::filesystem::directory_iterator Entry(std::filesystem::u8path(Folder), Error), End; !Error && Entry != End; Entry.increment(Error))
		{
			const std::filesystem::path& Path = Entry->path();
			const std::string Extension = Path.extension().string();
			const uint8 Kind = Extension == ".png" ? 2 : Extension == ".bc7" ? 1 : 0;
			if (Kind == 0)
			{
				continue;
			}
			if (const auto Name = BeetleTextureNameOf(Path.stem().string()))
			{
				uint8& Have = I.Pack[PackKey(Name->Upload, Name->Palette)];
				Have = std::max(Have, Kind);
			}
		}
		return Error ? "pack unreadable: " + Error.message() : std::string{};
	}

	void FSession::SetPictureReader(FReadPicture Reader)
	{
		Impl->Reader = std::move(Reader);
	}

	std::vector<uint8_t> FSession::PageImage(const std::string& Key, int& Size) const
	{
		return BuildPage(PageJob(Key), Impl->Reader, Size);
	}

	FPageJob FSession::PageJob(const std::string& Key) const
	{
		const FImpl& I = *Impl;
		FPageJob Job;
		Job.Texels.assign(256 * 256 * 4, 0);
		const FVram* SceneVram = I.SceneVram();
		if (SceneVram == nullptr || Key.size() < 5)
		{
			return Job;
		}
		const uint32 View = static_cast<uint32>(std::strtoul(Key.c_str() + 5, nullptr, 16));
		const FTexturePage Page = TextureViewPage(View);
		const FClutPosition Clut = TextureViewClut(View);
		const FVram& Vram = *SceneVram;
		// The page's own texels through its CLUT.
		for (int V = 0; V < 256; ++V)
		{
			for (int U = 0; U < 256; ++U)
			{
				uint16 Texel = 0;
				if (Page.Depth == ETextureDepth::Indexed4)
				{
					const uint16 Word = Vram.TexelAt(Page.X + (U >> 2), Page.Y + V);
					Texel = Vram.TexelAt(Clut.X + (Word >> ((U & 3) * 4) & 15), Clut.Y);
				}
				else if (Page.Depth == ETextureDepth::Indexed8)
				{
					const uint16 Word = Vram.TexelAt(Page.X + (U >> 1), Page.Y + V);
					Texel = Vram.TexelAt(Clut.X + (Word >> ((U & 1) * 8) & 255), Clut.Y);
				}
				else
				{
					Texel = Vram.TexelAt(Page.X + U, Page.Y + V);
				}
				uint8_t* Pixel = &Job.Texels[(static_cast<std::size_t>(V) * 256 + U) * 4];
				if (Texel != 0)
				{
					Pixel[0] = static_cast<uint8_t>((Texel & 31) * 255 / 31);
					Pixel[1] = static_cast<uint8_t>((Texel >> 5 & 31) * 255 / 31);
					Pixel[2] = static_cast<uint8_t>((Texel >> 10 & 31) * 255 / 31);
					Pixel[3] = 255;
				}
			}
		}
		// Each upload the pack has a picture of.
		Job.Per = TexelsPerUnit(Page.Depth);
		for (const FBeetleTexturePart& Part : BeetleTextureParts(Vram, FImpl::WholePage(View)))
		{
			const uint64 Name = I.PictureName(Vram, View, Part);
			const uint8* Kind = Name != 0 ? I.InPack(Name) : nullptr;
			if (Kind == nullptr)
			{
				continue;
			}
			Job.Parts.push_back({I.PathOf(Name, *Kind), Part.U, Part.V, Part.Width, Part.Height, Part.FromU, Part.FromV, Part.UploadUnitsWide,
				Part.UploadUnitsHigh});
		}
		return Job;
	}

	std::vector<uint8_t> FSession::BuildPage(const FPageJob& Job, const FReadPicture& Reader, int& Size)
	{
		Size = 256 * PageScale;
		std::vector<uint8_t> Out(static_cast<std::size_t>(Size) * Size * 4, 0);
		const auto Put = [&](int X, int Y, const uint8_t* Rgb, bool bVisible) {
			uint8_t* Pixel = &Out[(static_cast<std::size_t>(Y) * Size + X) * 4];
			Pixel[0] = bVisible ? Rgb[0] : 0;
			Pixel[1] = bVisible ? Rgb[1] : 0;
			Pixel[2] = bVisible ? Rgb[2] : 0;
			Pixel[3] = bVisible ? 255 : 0;
		};
		// The page's own texels, each PageScale square.
		if (Job.Texels.size() == 256 * 256 * 4)
		{
			for (int V = 0; V < 256; ++V)
			{
				for (int U = 0; U < 256; ++U)
				{
					const uint8_t* Texel = &Job.Texels[(static_cast<std::size_t>(V) * 256 + U) * 4];
					for (int Y = 0; Y < PageScale; ++Y)
					{
						for (int X = 0; X < PageScale; ++X)
						{
							Put(U * PageScale + X, V * PageScale + Y, Texel, Texel[3] != 0);
						}
					}
				}
			}
		}
		if (!Reader)
		{
			return Out;
		}
		// Each upload the pack has a picture of, as Beetle scales it: whole picture units per upload unit and rows per row.
		const int Per = Job.Per;
		std::vector<uint8_t> Picture;
		for (const FPageJob::FPart& Part : Job.Parts)
		{
			int Width = 0, Height = 0;
			if (!Reader(Part.Path, Picture, Width, Height))
			{
				continue;
			}
			const int PerUnit = Width / std::max<int>(1, Part.UploadUnitsWide);
			const int PerRow = Height / std::max<int>(1, Part.UploadUnitsHigh);
			if (PerUnit == 0 || PerRow == 0)
			{
				continue;
			}
			const double ScaleU = static_cast<double>(PerUnit) / Per;
			for (int Y = 0; Y < Part.Height * PageScale; ++Y)
			{
				const int From = std::min(Height - 1, static_cast<int>((Part.FromV + (Y + 0.5) / PageScale) * PerRow));
				for (int X = 0; X < Part.Width * PageScale; ++X)
				{
					const int Across = std::min(Width - 1, static_cast<int>((Part.FromU + (X + 0.5) / PageScale) * ScaleU));
					const uint8_t* Source = &Picture[(static_cast<std::size_t>(From) * Width + Across) * 4];
					const int ToX = Part.U * PageScale + X, ToY = Part.V * PageScale + Y;
					if (ToX < Size && ToY < Size)
					{
						// The pack's rule: only (0, 0, 0, 0) is transparent.
						Put(ToX, ToY, Source, (Source[0] | Source[1] | Source[2] | Source[3]) != 0);
					}
				}
			}
		}
		return Out;
	}

	void FSession::SetLazyTextures(bool bLazy)
	{
		Impl->bLazy = bLazy;
	}

	void FSession::MarkTextureReady(const std::string& Key)
	{
		Impl->Ready.insert(Key);
		Impl->Wanted.erase(Key);
	}

	void FSession::ForgetReadyPages()
	{
		Impl->ForgetReadyPages();
	}

	std::vector<uint8_t> FSession::TexelKinds(const std::string& Key, int& Width, int& Height) const
	{
		const auto Found = Impl->KindsOf.find(Key);
		if (Found == Impl->KindsOf.end())
		{
			Width = Height = 0;
			return {};
		}
		Width = Found->second.Width;
		Height = Found->second.Height;
		return Found->second.Blends;
	}

	bool FSession::TexelKindsMixed(const std::string& Key) const
	{
		const auto Found = Impl->KindsOf.find(Key);
		return Found != Impl->KindsOf.end() && Found->second.bMixed;
	}

	std::vector<std::string> FSession::TakeWantedTextures()
	{
		std::vector<std::string> Out(Impl->Wanted.begin(), Impl->Wanted.end());
		Impl->Wanted.clear();
		return Out;
	}

	std::string FSession::SetPagePack(const std::string& Folder)
	{
		FImpl& I = *Impl;
		I.PagePack.clear();
		I.PagePackFolder = Folder;
		std::error_code Error;
		for (std::filesystem::directory_iterator Entry(std::filesystem::u8path(Folder), Error), End; !Error && Entry != End; Entry.increment(Error))
		{
			const std::string Extension = Entry->path().extension().string();
			const uint8 Kind = Extension == ".png" ? 2 : Extension == ".bc7" ? 1 : 0;
			if (const auto Name = Kind != 0 ? BeetleTextureNameOf(Entry->path().stem().string()) : std::nullopt)
			{
				uint8& Have = I.PagePack[PackKey(Name->Upload, Name->Palette)];
				Have = std::max(Have, Kind);
			}
		}
		return Error ? "page pack unreadable: " + Error.message() : std::string{};
	}

	int FSession::PackPictures() const
	{
		return static_cast<int>(Impl->Pack.size());
	}

	void FSession::SetOptions(const FDrawOptions& Options)
	{
		Impl->Options = Options;
		Impl->ForgetScenery();
	}

	std::string FSession::EnterField(int Number)
	{
		FImpl& I = *Impl;
		if (!I.Session)
		{
			return "not open";
		}
		if (!Testing::CopyNewGameParty(I.Disc->Image(), *I.Index, I.Session->Game()))
		{
			return "new-game party file missing";
		}
		auto Loop = FGameLoop::EnterField(*I.Session, static_cast<uint16>(Number));
		if (!Loop)
		{
			return Loop.Error().Message;
		}
		I.Loop = std::move(*Loop);
		I.ResetScreens();
		I.RollFrom(std::nullopt, "");
		return {};
	}

	std::string FSession::EnterFieldKeeping(int Number)
	{
		FImpl& I = *Impl;
		if (!I.Session)
		{
			return "not open";
		}
		auto Loop = FGameLoop::EnterField(*I.Session, static_cast<uint16>(Number));
		if (!Loop)
		{
			return Loop.Error().Message;
		}
		I.Loop = std::move(*Loop);
		I.ForgetGame();
		return {};
	}

	std::string FSession::EnterWorldMap(int Story, int Scene, int Entrance)
	{
		FImpl& I = *Impl;
		if (!I.Session)
		{
			return "not open";
		}
		if (!Testing::CopyNewGameParty(I.Disc->Image(), *I.Index, I.Session->Game()))
		{
			return "new-game party file missing";
		}
		// The world map's places are numbered from 400h; the story's progress is the first saved event variable.
		constexpr uint16 FirstWorldMapPlace = 0x400;
		FGameState& Game = I.Session->Game();
		Game.SetSavedEventVariable(0, static_cast<uint16>(Story));
		Game.SetWorldMapPlace(FirstWorldMapPlace, static_cast<uint16>(Entrance), 0, static_cast<uint16>(Scene));
		auto Loop = FGameLoop::EnterWorldMap(*I.Session);
		if (!Loop)
		{
			return Loop.Error().Message;
		}
		I.Loop = std::move(*Loop);
		I.ResetScreens();
		I.RollFrom(std::nullopt, "");
		return {};
	}

	std::vector<int> FSession::WorldMapArrivals() const
	{
		std::vector<int> Ids;
		if (const FWorldMapProgram* Map = Impl->WorldMap())
		{
			for (const FWorldMapEntrance& Arrival : Map->Runtime().Scene().Entrances)
			{
				Ids.push_back(Arrival.Id);
			}
		}
		return Ids;
	}

	std::string FSession::AskBattling(const std::array<int, 6>& Parameters)
	{
		FImpl& I = *Impl;
		FFieldProgram* Running = I.Loop ? I.Loop->Field() : nullptr;
		if (Running == nullptr)
		{
			return "no field runs";
		}
		// As FE BF leaves the field's requests (EventOpsPrograms.cpp, StartBattling).
		FEventRequests& Requests = Running->Runtime().Context().Requests;
		for (std::size_t Byte = 0; Byte < Parameters.size(); ++Byte)
		{
			Requests.BattlingParameters[Byte] = static_cast<uint8>(Parameters[Byte]);
		}
		Requests.bLeavingField = true;
		Requests.bBattling = true;
		++I.CheatsSince;
		return {};
	}

	std::string FSession::AskFieldMovie(int Number, int EndFrame)
	{
		FImpl& I = *Impl;
		FFieldProgram* Running = I.Loop ? I.Loop->Field() : nullptr;
		if (Running == nullptr)
		{
			return "no field runs";
		}
		// As FE 60 of kind 2 leaves the request (full screen, 24-bit colour), skippable.
		constexpr uint16 FullScreenTrueColour = 2;
		constexpr int16 ScreenWidth = 0x140;
		constexpr int16 PictureHeight = 0x100;
		constexpr int16 LowerBuffer = 0x100;
		FEventContext& Context = Running->Runtime().Context();
		FFieldMovieRequest& Movie = Context.Requests.Movie;
		Movie = {};
		Movie.Movie = static_cast<uint16>(Number);
		Movie.StartFrame = 1;
		Movie.EndFrame = static_cast<uint16>(EndFrame);
		Movie.Flags = FFieldMovieRequest::Skippable;
		Movie.Kind = FullScreenTrueColour;
		Movie.Width = ScreenWidth;
		Movie.Height = PictureHeight;
		Movie.Buffers = {0, 0, 0, LowerBuffer};
		Movie.bTrueColour = true;
		Context.MovieView = EFieldMovieView::FullScreen;
		Context.Requests.bMovie = true;
		++I.CheatsSince;
		return {};
	}

	std::string FSession::DebugBattlingSites(int First, int Last) const
	{
		const FImpl& I = *Impl;
		if (!I.Session)
		{
			return "not open\n";
		}
		std::string Out;
		char Line[256];
		constexpr uint8 StartBattling = 0xBF;
		for (int Map = std::max(First, 0); Map <= std::min(Last, FieldMapCount - 1); ++Map)
		{
			auto Archive = LoadFieldArchive(I.Disc->Image(), *I.Index, Map);
			if (!Archive)
			{
				continue;
			}
			const std::vector<uint8>& Code = Archive->Section(EFieldSection::EventScripts);
			for (std::size_t At = 0; At + 1 < Code.size(); ++At)
			{
				if (Code[At] != EventOpcode::ExtendedPrefix || Code[At + 1] != StartBattling)
				{
					continue;
				}
				const std::optional<FEventInstruction> Read = ReadEventInstruction(Code, At);
				if (!Read || Read->Shape == nullptr || Read->Operands == nullptr || Read->Operands->Count != 6)
				{
					continue;
				}
				std::snprintf(Line, sizeof(Line), "map %d at %zu:", Map, At);
				Out += Line;
				for (int Operand = 0; Operand < 6; ++Operand)
				{
					const int32 Value = Read->Values[static_cast<std::size_t>(Operand)];
					// A Value operand: a constant of 15 bits where bit 15 is set, else a variable's address.
					if ((Value & 0x8000) != 0)
					{
						std::snprintf(Line, sizeof(Line), " %d", Value & 0x7FFF);
					}
					else
					{
						std::snprintf(Line, sizeof(Line), " v%04x", Value & 0xFFFF);
					}
					Out += Line;
				}
				Out += "\n";
			}
		}
		return Out;
	}

	std::string FSession::PowerOn()
	{
		FImpl& I = *Impl;
		if (!I.Session)
		{
			return "not open";
		}
		auto Loop = FGameLoop::PowerOn(*I.Session, *I.Executable);
		if (!Loop)
		{
			return Loop.Error().Message;
		}
		I.Loop = std::move(*Loop);
		I.ResetScreens();
		I.RollFrom(std::nullopt, "");
		return {};
	}

	std::string FSession::LoadCard(const std::string& CardPath, int Slot, std::string& Listing)
	{
		FImpl& I = *Impl;
		if (!I.Session)
		{
			return "not open";
		}
		std::ifstream File(std::filesystem::u8path(CardPath), std::ios::binary);
		const std::vector<uint8> Bytes((std::istreambuf_iterator<char>(File)), std::istreambuf_iterator<char>());
		auto Saves = ReadCardImageSaves(Bytes);
		if (!Saves)
		{
			return Saves.Error().Message;
		}
		char Line[160];
		for (std::size_t Save = 0; Save < Saves->size(); ++Save)
		{
			const FOriginalSave& Found = (*Saves)[Save];
			const auto Party = Found.Party();
			std::snprintf(Line, sizeof(Line), "%zu: story %u, played %u s, party %u %u %u\n", Save, Found.StoryProgress(), Found.PlayTime(), Party[0],
				Party[1], Party[2]);
			Listing += Line;
		}
		if (Slot < 0)
		{
			return {};
		}
		if (static_cast<std::size_t>(Slot) >= Saves->size())
		{
			return "no save " + std::to_string(Slot) + " on the card";
		}
		const auto Tables = FGearPartTables::Load(I.Disc->Image(), *I.Index);
		if (!Tables)
		{
			return Tables.Error().Message;
		}
		auto Loaded = LoadOriginalSave((*Saves)[static_cast<std::size_t>(Slot)], I.Session->Game(), *Tables, I.Session->Text().NameTables);
		if (!Loaded)
		{
			return Loaded.Error().Message;
		}
		FGameState& Game = I.Session->Game();
		Game = std::move(*Loaded);
		// As the game's own load leaves it (Tests/Support/StorySweepExplore.cpp): the party by the save point.
		constexpr int32 LoadedEntrance = 0x2A;
		constexpr uint8 LoadedResult = 2;
		constexpr uint16 PlaceMapBits = 0x3FFF;
		const bool bWorldMap = LoadedGameProgram(Game) == EGameProgram::WorldMap;
		if (!bWorldMap)
		{
			Game.SetFieldEntrance(Game.SavedEventVariable(LoadedEntrance));
		}
		Game.ProgramResult = LoadedResult;
		auto Loop = bWorldMap ? FGameLoop::EnterWorldMap(*I.Session) : FGameLoop::EnterField(*I.Session, static_cast<uint16>(Game.Place() & PlaceMapBits));
		if (!Loop)
		{
			return Loop.Error().Message;
		}
		I.Loop = std::move(*Loop);
		I.ResetScreens();
		I.RollFrom(std::nullopt, "");
		return {};
	}

	std::string FSession::SaveState(const std::string& Path)
	{
		FImpl& I = *Impl;
		if (!I.Loop)
		{
			return "no game running";
		}
		auto Captured = CaptureSaveState(*I.Loop, *I.Session);
		if (!Captured)
		{
			return Captured.Error().Message;
		}
		if (!*Captured)
		{
			return "not now: only where the player has control";
		}
		const std::vector<uint8> Bytes = WriteSaveState(**Captured);
		std::ofstream File(std::filesystem::u8path(Path), std::ios::binary);
		File.write(reinterpret_cast<const char*>(Bytes.data()), static_cast<std::streamsize>(Bytes.size()));
		// F6's state to go back to from now on (the game goes on from this moment unbroken).
		I.RollFrom(std::move(*Captured), "F5's state");
		return File ? std::string{} : "cannot write " + Path;
	}

	std::string FSession::LoadState(const std::string& Path)
	{
		FImpl& I = *Impl;
		if (!I.Session)
		{
			return "not open";
		}
		std::ifstream File(std::filesystem::u8path(Path), std::ios::binary);
		const std::vector<uint8> Bytes((std::istreambuf_iterator<char>(File)), std::istreambuf_iterator<char>());
		ESaveStateFault Fault = ESaveStateFault::NotAState;
		const auto State = ReadSaveState(Bytes, Fault);
		if (!State)
		{
			return Fault == ESaveStateFault::OtherVersion ? "a state of another version" : Fault == ESaveStateFault::Damaged ? "a damaged state" : "not a state";
		}
		// A state of the other disc: the drive looks for it (FImpl::SeekDisc) and keeps it for the session powered on below.
		const int Waited = I.WantedDisc;
		if (!I.Session->HasDisc(State->Kernel.Disc))
		{
			// The game does not wait on it for this: the line says what is missing, the game goes on as it was.
			I.WantedDisc = Waited;
			return "a state of disc " + std::to_string(State->Kernel.Disc + 1) + ", whose image is not where the game looks";
		}
		if (I.Loop)
		{
			// A game runs: as Weltall's Start, the loop and the session go, the sound starts afresh (nothing of the old
			// game's sound is left to be heard), and the console powers on again before it takes the state.
			I.Loop.reset();
			I.Session.reset();
			I.Unheard.reset();
			I.Sound.reset();
			auto Sound = I.StartSound();
			if (!Sound)
			{
				return Sound.Error().Message;
			}
			I.Sound = std::move(*Sound);
			I.Unheard = std::make_unique<FUnheardGameSound>(*I.Sound->Sound());
			if (I.bHeard)
			{
				I.Sound->Sound()->SetHeard(static_cast<uint32>(std::max(I.HeardLatency, 0)));
			}
			I.ForgetGame();
			if (std::string Error = I.PowerOn(); !Error.empty())
			{
				return Error;
			}
		}
		auto Loop = LoadSaveState(*I.Session, *State);
		if (!Loop)
		{
			// The console that held the state runs nothing: it powers on afresh, as a reset starts it (GameLoopScreenStates.cpp).
			std::string Why = Loop.Error().Message;
			I.Session.reset();
			I.ForgetGame();
			if (I.PowerOn().empty())
			{
				if (auto Started = FGameLoop::PowerOn(*I.Session, *I.Executable))
				{
					I.Loop = std::move(*Started);
				}
			}
			return Why;
		}
		I.Loop = std::move(*Loop);
		I.ResetScreens();
		// F6's state to go back to: the one loaded (the game goes on from it).
		I.RollFrom(*State, "the state loaded");
		return {};
	}

	std::string FSession::SetSaveFolder(const std::string& Folder)
	{
		FImpl& I = *Impl;
		std::error_code Error;
		std::filesystem::create_directories(std::filesystem::u8path(Folder), Error);
		if (Error)
		{
			return "cannot make " + Folder + ": " + Error.message();
		}
		auto Store = std::make_unique<FSaveStore>(std::filesystem::u8path(Folder));
		if (I.Session)
		{
			I.Session->SetSaves(Store.get());
		}
		I.Saves = std::move(Store);
		return {};
	}

	std::string FSession::Step(uint16_t Buttons, uint8_t StickX, uint8_t StickY, bool bAnalog)
	{
		FImpl& I = *Impl;
		if (!I.Loop)
		{
			return "no game running";
		}
		FPadState Held;
		Held.Buttons = Buttons;
		Held.StickX = StickX;
		Held.StickY = StickY;
		Held.bAnalog = bAnalog;
		const std::vector<FPadState> PerVblank(static_cast<std::size_t>(I.Loop->VblanksPerFrame()), Held);
		// Exactly one consumer passes the sound's time: unheard, the frame's own (the run stays the same however fast it
		// goes); heard, the listener as it takes the samples (RenderSound).
		if (!I.bHeard)
		{
			I.Unheard->Advance(PsxTiming::FrameSeconds * static_cast<double>(PerVblank.size()));
		}
		auto Error = I.Loop->Frame(PerVblank);
		I.AfterFrame();
		if (Error)
		{
			return Error->Message;
		}
		// A disc the game waits on is looked for again now and then (the game itself asks only as the player confirms):
		// found, the session has it, and the player's next confirmation goes on with it.
		if (I.WantedDisc >= 0 && std::chrono::duration<double>(std::chrono::steady_clock::now() - I.DiscLookedAt).count() >= FImpl::DiscLookSeconds)
		{
			I.DiscLookedAt = std::chrono::steady_clock::now();
			if (I.Session->HasDisc(I.WantedDisc))
			{
				I.WantedDisc = -1;
			}
		}
		I.InputsSince.push_back(Buttons);
		I.VblanksSince += static_cast<long long>(PerVblank.size());
		I.TurboStepsSince += GamePace() > 1 ? 1 : 0;
		if (I.RollingEvery > 0 && static_cast<long long>(I.InputsSince.size()) >= I.RollingEvery)
		{
			// F6's state to go back to, taken anew once RollingEvery frames have run since it; where the game is not quiet the
			// try finds so at once, and is made again the next frame (story_walk.cpp's rolling state, RollingEvery).
			const auto Started = std::chrono::steady_clock::now();
			auto Captured = CaptureSaveState(*I.Loop, *I.Session);
			const double Usec = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - Started).count();
			++I.RollingTries;
			if (Captured && *Captured)
			{
				++I.RollingCaptures;
				I.RollingUsecTotal += Usec;
				I.RollingUsecLongest = std::max(I.RollingUsecLongest, Usec);
				I.RollFrom(std::move(*Captured), "a quiet moment");
			}
			else
			{
				I.RollingTryUsecLongest = std::max(I.RollingTryUsecLongest, Usec);
			}
		}
		return {};
	}

	void FSession::SetRollingState(int Every)
	{
		Impl->RollingEvery = std::max(Every, 0);
	}

	FRollingStats FSession::RollingStats() const
	{
		const FImpl& I = *Impl;
		return {I.RollingEvery, I.RollingTries, I.RollingCaptures, I.RollingUsecTotal, I.RollingUsecLongest, I.RollingTryUsecLongest};
	}

	FReportState FSession::WriteReportState(const std::string& Path)
	{
		FImpl& I = *Impl;
		FReportState Out;
		if (!I.Loop || !I.Session)
		{
			Out.Error = "no game running";
			return Out;
		}
		// The game now, where it is quiet (taken on copies: the game plays on); else the newest state taken before.
		const FSaveState* Written = nullptr;
		auto Captured = CaptureSaveState(*I.Loop, *I.Session);
		if (Captured && *Captured)
		{
			Written = &**Captured;
			Out.Source = "now";
		}
		else
		{
			Out.Error = !Captured ? Captured.Error().Message : "not now: only where the player has control";
			if (I.Rolling)
			{
				Written = &*I.Rolling;
				Out.Source = I.RollingFrom;
				Out.Inputs = I.InputsSince;
				Out.Vblanks = I.VblanksSince;
				Out.TurboFrames = I.TurboStepsSince;
				Out.Cheats = I.CheatsSince;
				Out.Seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - I.RollingAt).count();
			}
		}
		if (Written == nullptr)
		{
			Out.Error += "; no state taken since the game began (no quiet moment yet, F5 not pressed, no state loaded)";
			return Out;
		}
		const std::vector<uint8> Bytes = WriteSaveState(*Written);
		std::ofstream File(std::filesystem::u8path(Path), std::ios::binary);
		File.write(reinterpret_cast<const char*>(Bytes.data()), static_cast<std::streamsize>(Bytes.size()));
		if (!File)
		{
			Out.Error = "cannot write " + Path;
			Out.Source.clear();
		}
		return Out;
	}

	std::string FSession::FrameReport()
	{
		FImpl& I = *Impl;
		FImpl::FFrameReport Report;
		std::vector<FSurface> World, Screen;
		Report.Lines = "== The world (the scene: scenery, models, sprites, particles; a battle's, the world map's, the arena's scene)\n";
		I.Report = &Report;
		BuildWorld(World);
		I.Report->Lines += "== The 2D layer\n";
		I.Report->Who.clear();
		BuildScreen(Screen);
		I.Report = nullptr;

		// The notes by kind, name and why: how many drawings, the upload's size and place, whose (a few).
		struct FGroup
		{
			const FImpl::FReportMiss* First = nullptr;
			int Count = 0;
			std::set<std::string> Whos;
		};
		std::map<std::tuple<int, std::string, std::string>, FGroup> Groups;
		const std::array<const char*, 4> Kinds{"sprite", "2D", "model", "other"};
		for (const FImpl::FReportMiss& Miss : Report.Misses)
		{
			const int Kind = static_cast<int>(std::find(Kinds.begin(), Kinds.end(), Miss.Kind) - Kinds.begin());
			FGroup& Group = Groups[{Kind, Miss.Name, Miss.Why}];
			Group.First = Group.First != nullptr ? Group.First : &Miss;
			++Group.Count;
			Group.Whos.insert(Miss.Who);
		}
		std::string Out = "== Drawn not from the pack (this frame, built again for the report)\n";
		if (!I.Options.bHd || I.Pack.empty())
		{
			Out += "The pack is off (F3) or not read: everything is drawn from VRAM, the list below is every upload drawn.\n";
		}
		const FFrameInfo Shown = Info();
		char Line[512];
		std::snprintf(Line, sizeof(Line),
			"Sprite pieces %d: wholly from the pack %d, partly %d, from VRAM %d (waiting for a picture %d). 2D textured %d, from the pack %d (waiting %d). "
			"Scenery polygons from pages with pictures %d (partly over uploads without one %d), from VRAM %d.\n",
			Shown.SpritePieces, Shown.SpriteHd, Shown.SpritePartial, Shown.SpriteVram, Shown.SpriteWaiting, Shown.ScreenTextured, Shown.ScreenHd,
			Shown.ScreenWaiting, Shown.SceneryHd, Shown.SceneryHdMixed, Shown.SceneryVram);
		Out += Line;
		const std::array<const char*, 4> Titles{"-- Sprite pieces (a battle's quads among them)", "-- 2D primitives", "-- Models' textures (scenery, gears, objects; figures drawn on models among them)",
			"-- Other (particles, effects, the world map's pieces)"};
		std::set<std::string> Lacking;
		for (int Kind = 0; Kind < static_cast<int>(Kinds.size()); ++Kind)
		{
			std::vector<std::pair<const std::tuple<int, std::string, std::string>*, const FGroup*>> Rows;
			for (const auto& [Key, Group] : Groups)
			{
				if (std::get<0>(Key) == Kind)
				{
					Rows.push_back({&Key, &Group});
				}
			}
			std::snprintf(Line, sizeof(Line), "%s: %zu name(s)\n", Titles[static_cast<std::size_t>(Kind)], Rows.size());
			Out += Line;
			std::stable_sort(Rows.begin(), Rows.end(), [](const auto& A, const auto& B) { return A.second->Count > B.second->Count; });
			for (const auto& [Key, Group] : Rows)
			{
				const FImpl::FReportMiss& Miss = *Group->First;
				Out += "  " + std::get<1>(*Key);
				if (Miss.UnitsWide > 0)
				{
					std::snprintf(Line, sizeof(Line), "  %dx%d units (%dx%d texels) at VRAM %d,%d", Miss.UnitsWide, Miss.UnitsHigh, Miss.UnitsWide * Miss.Per,
						Miss.UnitsHigh, Miss.UploadX, Miss.UploadY);
					Out += Line;
				}
				Out += "  drawn " + std::to_string(Group->Count) + "x  " + std::get<2>(*Key) + "\n    by: ";
				int Listed = 0;
				for (const std::string& Who : Group->Whos)
				{
					if (Listed++ == 4)
					{
						Out += "; and " + std::to_string(Group->Whos.size() - 4) + " more";
						break;
					}
					Out += (Listed > 1 ? "; " : "") + (Who.empty() ? std::string("-") : Who);
				}
				Out += "\n";
				const std::string& Why = std::get<2>(*Key);
				if (std::get<1>(*Key) != "-" && (Why.find("not in the pack") != std::string::npos || Why.find("this upload none") != std::string::npos
						|| Why.find("no upload on its page") != std::string::npos))
				{
					Lacking.insert(std::get<1>(*Key));
				}
			}
		}
		Out += "-- Names the pack lacks (no picture by this name, none found by content), one a line: " + std::to_string(Lacking.size()) + "\n";
		for (const std::string& Name : Lacking)
		{
			Out += Name + "\n";
		}
		Out += "== What the frame holds that the bridge leaves undrawn or draws by a stand-in (classes with a count)\n";
		for (const FUnhandled& Class : Unhandled())
		{
			if (Class.Count != 0)
			{
				Out += std::string("  ") + Class.Name + " " + std::to_string(Class.Count) + "\n";
			}
		}
		Out += "== Every primitive of the frame (the lines of XENO_DUMP_2D, XENO_DUMP_OBJECTS, XENO_TALLY_LOG=2; the field's polygons and sprite pieces)\n";
		Out += Report.Lines;
		return Out;
	}

	void FSession::FImpl::AfterFrame()
	{
		FImpl& I = *this;
		// A battle's transition breaks the picture of the screen before it (BattleView.cpp, Follow: taken as the program starts).
		I.BattleScreenBefore = I.Loop->Battle() != nullptr ? FImpl::BattlePictureKey(I.Loop->ProgramRuns()) : 0;
		if (FWorldMapProgram* Map = I.Loop->WorldMap())
		{
			// As Weltall's game screen runs the world map (GameLoopScreen.cpp, GameLoopWorldMapCulling): everything a view of
			// any width shows within the original's reach (the display's window is wider than 320), from its next tick on.
			Map->SetCulling(EWorldMapCulling::InRange);
			// A new run of the program fades the screen before it: the display gives that picture under a key of its own.
			const int Key = FImpl::MapPictureKey(I.Loop->ProgramRuns());
			if (Key != I.MapScreenBefore)
			{
				I.MapScreenBefore = Key;
				I.MapAnimated.clear();
			}
			I.FollowMapAnimations(*Map);
		}
		else if (I.Loop->Battling() != nullptr)
		{
			// The arena's frame is drawn by the world map's path: the rectangles a world map's animations wrote are not its.
			I.MapAnimated.clear();
		}
		I.FollowScreens();
	}

	namespace
	{
		/**
		 * The classes of what a frame holds that BuildWorld and BuildScreen leave undrawn or draw by a stand-in, in the order
		 * Unhandled gives them: each named after the core's field or link it reads, with what the bridge does with it.
		 */
		constexpr std::array<const char*, 28> UnhandledClasses{
			"blank_screen", // a program runs and nothing is drawn: no screen kind for it (the debug menu; the Battling arena until 14.11)
			"battling_program", // the Battling arena's frames (in the world map's frame form): drawn since 14.11 (AddMapScene, PushArenaLayer), counted for checks
			"battling_unframed", // the arena runs and has drawn no frame yet: nothing drawn (black, as Weltall's view before its first frame)
			"battling_pause_blur", // a paused frame's picture (PictureBlurs): drawn without its blurs (the 2D layer over it as the game draws it)
			"battling_trails", // the menus' demonstration (bTrails): each frame over a cleared screen, not over the one before dimmed
			"battling_scene_blended", // semi-transparent triangles of the arena's scene (effects, shadows): blended in linear light in a float buffer
			"battle_transition", // the battle's opening transition (DefaultTransition / SetupTransition): drawn since 13.11 (PushBattleTransition), counted for checks
			"battle_unbegun", // the battle runs, its show not begun and no transition: nothing drawn
			"battle_screen_wave", // the battle's screen wave (FBattleShow::ScreenWave running): the screen drawn without its waving
			"battle_scene_blended", // semi-transparent triangles of the battle's scene: blended in Godot's linear float buffer, not as the PS1's 8 bits
			"battle_tiles", // tiles, lines, screen quads, model polygons, cloths, trails of a battle frame: code carried over, never seen drawn
			"field_gears", // a gear's model the field draws (Order entries of kind Gear): drawn since 13.11 (AddFieldGears), counted for checks
			"field_sprite_models", // a spawned child's model (Order entries of kind SpriteModel): drawn since 13.11 (AddFieldSpriteModels), counted for checks
			"field_scrolled_models", // placed models whose texture coordinates the scripts scroll (ScrolledModels, U or V not 0): drawn unscrolled
			"field_screen_wave", // the field's screen wave (bScreenWave): drawn since 13.11 (ScreenWave, main.gd), counted for checks
			"field_draw_clip", // the scene clipped to a part of the screen (DrawClip not the whole 320 x 224): drawn unclipped
			"field_cover_from_vram", // the picture of the screen drawn from VRAM's picture area (Cover shown, not bScreen): not drawn
			"field_frame_of_map_before", // a frame of the map before (its scenery is not the scene's): nothing of the world drawn
			"field_order_by_depth", // the field's entries drawn through the depth buffer, not in the frame's Order (the PS1's painter's order)
			"world_soft_blend", // semi-transparent triangles of the field's and the world map's scene: blended in linear light in a float buffer
			"map_waver", // the world map's screen waver (WaverShifts not 0): drawn without it
			"map_gear_or_arena", // world map polygons of the Gear or Effect layer (a gear's model, the arena's effects): drawn as polygons, never checked
			"menu_gear_shop_model", // the gear shop's model under its menu (FMenuProgram::GearModel): not drawn
			"button_glyphs", // the player's button pictures in message text (TextButtons): the game's own glyphs drawn
			"sprites_from_vram", // sprite pieces not wholly from the pack (SpritePartial + SpriteVram of the last BuildWorld)
			"screen_2d_from_vram", // textured 2D primitives not from the pack (ScreenTextured - ScreenHd of the last BuildScreen)
			"scenery_from_vram", // scenery polygons from VRAM, or on a page partly outside the pack's pictures (SceneryVram + SceneryHdMixed)
			"waiting_textures", // primitives drawn from VRAM while their picture loads (lazy textures; 0 headless)
		};
	}

	std::vector<float> FSession::ScreenWave() const
	{
		const FImpl& I = *Impl;
		std::vector<float> Out;
		const FFieldFrame* Frame = I.Field() != nullptr && I.ScreenNow() == EScreenKind::Field ? I.Frame() : nullptr;
		if (Frame == nullptr || FImpl::WithoutTask7() || !Frame->bScreenWave || Frame->WideWave.size() != static_cast<std::size_t>(FFieldScreenWave::WideColumns * FFieldScreenWave::Rows))
		{
			return Out;
		}
		// The wide grid (FFieldScreenWave::BuildWideCells): columns from WideMargin left of the screen's first, 16 pixels each.
		constexpr int32 Cell = FFieldScreenWave::CellSize;
		for (int32 Row = 0; Row < FFieldScreenWave::Rows; ++Row)
		{
			for (int32 Column = 0; Column < FFieldScreenWave::WideColumns; ++Column)
			{
				const FFieldScreenWaveCell& Waved = Frame->WideWave[static_cast<std::size_t>(Row * FFieldScreenWave::WideColumns + Column)];
				const int32 Left = (Column - FFieldScreenWave::WideMargin) * Cell, Top = Row * Cell;
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					Out.insert(Out.end(), {static_cast<float>(Waved.Corners[Corner][0]), static_cast<float>(Waved.Corners[Corner][1]),
						static_cast<float>(Left + ((Corner & 1) != 0 ? Cell : 0)), static_cast<float>(Top + ((Corner & 2) != 0 ? Cell : 0))});
				}
			}
		}
		return Out;
	}

	std::vector<const char*> FSession::UnhandledNames()
	{
		return {UnhandledClasses.begin(), UnhandledClasses.end()};
	}

	std::vector<FUnhandled> FSession::Unhandled() const
	{
		const FImpl& I = *Impl;
		std::array<int, UnhandledClasses.size()> Counts{};
		const auto Count = [&](const char* Name, int By)
		{
			for (std::size_t Index = 0; Index < UnhandledClasses.size(); ++Index)
			{
				if (std::string_view(UnhandledClasses[Index]) == Name)
				{
					Counts[Index] += By;
					return;
				}
			}
		};
		if (I.Loop && I.Loop->Stage() == EGameLoopStage::Program)
		{
			if (I.ScreenNow() == EScreenKind::Blank)
			{
				Count("blank_screen", 1);
			}
			if (const FBattlingGameProgram* Arena = I.Battling())
			{
				const FBattlingFrame* Latest = Arena->LatestFrame();
				Count("battling_program", 1);
				Count("battling_unframed", Latest == nullptr ? 1 : 0);
				Count("battling_pause_blur", Latest != nullptr && Latest->PictureBlurs > 0 ? 1 : 0);
				Count("battling_trails", Latest != nullptr && Latest->bTrails ? 1 : 0);
				Count("battling_scene_blended", I.WorldBlended);
				Count("button_glyphs", Latest != nullptr ? static_cast<int>(Latest->TextButtons.size()) : 0);
			}
			if (const FBattleGameProgram* Fight = I.Battle())
			{
				const bool bBegun = Fight->Presentation().HasBegun();
				if (Fight->Runtime().IsInTransition() && (Fight->Runtime().DefaultTransition() != nullptr || Fight->Runtime().SetupTransition() != nullptr))
				{
					Count("battle_transition", 1);
				}
				else if (!bBegun)
				{
					Count("battle_unbegun", 1);
				}
				if (bBegun && Fight->Presentation().Show.ScreenWave().IsRunning())
				{
					Count("battle_screen_wave", 1);
				}
				if (const FBattleShowFrame* Frame = I.BattleFrame())
				{
					int Rare = static_cast<int>(Frame->Tiles.size() + Frame->Lines.size() + Frame->ScreenQuads.size() + Frame->ModelPolygons.size());
					if (Frame->Objects != nullptr)
					{
						Rare += static_cast<int>(Frame->Objects->Cloths.size() + Frame->Objects->Trails.size());
					}
					Count("battle_tiles", Rare);
					Count("battle_scene_blended", I.WorldBlended);
				}
			}
			if (const FFieldProgram* Field = I.Field())
			{
				if (const FFieldFrame* Frame = I.Frame())
				{
					int Gears = 0, Children = 0;
					for (const FFieldDrawItem& Item : Frame->Order)
					{
						Gears += Item.Kind == EFieldDrawKind::Gear ? 1 : 0;
						Children += Item.Kind == EFieldDrawKind::SpriteModel ? 1 : 0;
					}
					Count("field_gears", Gears);
					Count("field_sprite_models", Children);
					Count("field_scrolled_models", static_cast<int>(std::count_if(Frame->ScrolledModels.begin(), Frame->ScrolledModels.end(),
						[](const FFieldScrolledModel& Model) { return Model.U != 0 || Model.V != 0; })));
					Count("field_screen_wave", Frame->bScreenWave && Frame->bSceneDrawn ? 1 : 0);
					const bool bWhole = Frame->DrawClip.X <= 0 && Frame->DrawClip.Y <= 0 && Frame->DrawClip.Width >= FFieldScreenWave::ScreenWidth
						&& Frame->DrawClip.Height >= FFieldScreenWave::ScreenHeight;
					Count("field_draw_clip", !bWhole && Frame->bSceneDrawn ? 1 : 0);
					Count("field_cover_from_vram", Frame->Cover.bShown && !Frame->Cover.bScreen ? 1 : 0);
					const FFieldScene& Scene = Field->Drawing().Scene();
					const bool bBefore = Frame->Scenery.Polygons.size() != Scene.Polygons.size() || Frame->Scenery.Objects.size() != Scene.Objects.size();
					Count("field_frame_of_map_before", bBefore && Frame->bSceneDrawn ? 1 : 0);
					if (Frame->bSceneDrawn && !bBefore)
					{
						Count("field_order_by_depth", static_cast<int>(Frame->Order.size()));
					}
					Count("button_glyphs", static_cast<int>(Frame->TextButtons.size()));
				}
				Count("world_soft_blend", I.WorldBlended);
			}
			if (const FWorldMapProgram* Map = I.WorldMap())
			{
				if (const FWorldMapFrame* Frame = Map->LatestFrame())
				{
					Count("map_waver", std::any_of(Frame->WaverShifts.begin(), Frame->WaverShifts.end(), [](int16 Shift) { return Shift != 0; }) ? 1 : 0);
					Count("map_gear_or_arena", static_cast<int>(std::count_if(Frame->Polygons.begin(), Frame->Polygons.end(), [](const FWorldMapPolygon& Polygon)
						{ return Polygon.Layer == EWorldMapLayer::Gear || Polygon.Layer == EWorldMapLayer::Effect; })));
				}
				Count("world_soft_blend", I.WorldBlended);
			}
			if (const FMenuProgram* Menu = I.RunningMenu())
			{
				Count("menu_gear_shop_model", Menu->GearModel() != nullptr ? 1 : 0);
			}
		}
		Count("sprites_from_vram", I.SpritePartial + I.SpriteVram);
		Count("screen_2d_from_vram", I.ScreenTextured - I.ScreenHd);
		Count("scenery_from_vram", I.SceneryVram + I.SceneryHdMixed);
		Count("waiting_textures", I.Waiting);
		std::vector<FUnhandled> Out;
		for (std::size_t Index = 0; Index < UnhandledClasses.size(); ++Index)
		{
			Out.push_back({UnhandledClasses[Index], Counts[Index]});
		}
		return Out;
	}

	void FSession::Observe(FGameSession* Session, FGameLoop* Loop)
	{
		FImpl& I = *Impl;
		if (I.bObserved)
		{
			(void)I.Loop.release();
			(void)I.Session.release();
		}
		else
		{
			I.Loop.reset();
			I.Session.reset();
		}
		I.bObserved = Session != nullptr && Loop != nullptr;
		if (!I.bObserved)
		{
			I.ObservedMenus = nullptr;
			I.ObservedSession = nullptr;
			I.ForgetGame();
			return;
		}
		// The story walk's run gives its sessions Weltall's FMenuGameMenus (StorySweepRun.cpp, Begin): no RTTI, so a static cast.
		I.ObservedMenus = static_cast<const FMenuGameMenus*>(Session->Menus());
		if (Session != I.ObservedSession)
		{
			// A new game powered on (the run begins anew from a state): nothing drawn from the one before holds.
			I.ObservedSession = Session;
			I.ForgetGame();
		}
		I.Session.reset(Session);
		I.Loop.reset(Loop);
		I.AfterFrame();
	}

	int FSession::VblanksPerFrame() const
	{
		return Impl->Loop ? Impl->Loop->VblanksPerFrame() : 2;
	}

	double FSession::VblankSeconds()
	{
		return PsxTiming::FrameSeconds;
	}

	int FSession::VblanksDue(double Seconds)
	{
		// As Weltall's game screen runs a fast-forward (GameLoopScreen.cpp, Update): the session told the pace (the play time
		// and the pads' repeat count the player's own time alone), the clock bringing that many times the vertical blanks.
		const int Pace = GamePace();
		if (Impl->Session)
		{
			Impl->Session->SetPace(Pace);
		}
		return Impl->Vblanks.Advance(Seconds, Pace);
	}

	int FSession::SoundRate()
	{
		return IGameSound::SampleRate;
	}

	int FSession::SoundLeadFrames()
	{
		return static_cast<int>(std::ceil(FTickClock::MaxTicksPerAdvance * PsxTiming::FrameSeconds * IGameSound::SampleRate));
	}

	std::string FSession::Hear(int LatencyFrames)
	{
		FImpl& I = *Impl;
		if (!I.Sound)
		{
			return "not open";
		}
		I.bHeard = true;
		I.HeardLatency = LatencyFrames;
		// As Weltall's UGameSoundSubsystem::Start tells the core (Source/Weltall/Private/Audio/GameSoundSubsystem.cpp): what
		// waits on the heard sound (a movie's pictures) follows it from now on.
		I.Sound->Sound()->SetHeard(static_cast<uint32>(std::max(LatencyFrames, 0)));
		return {};
	}

	bool FSession::Heard() const
	{
		return Impl->bHeard;
	}

	bool FSession::RenderSound(int16_t* Stereo, int Frames)
	{
		FImpl& I = *Impl;
		if (!I.bHeard || !I.Sound || Frames <= 0)
		{
			return false;
		}
		// The samples as Weltall's UGameSoundWave::OnGeneratePCMAudio takes them: the driver's interrupts run among them as
		// they fall due (FGameSoundSystem::Render).
		I.Sound->Sound()->Render(std::span<int16>(reinterpret_cast<int16*>(Stereo), static_cast<std::size_t>(Frames) * 2));
		return true;
	}

	std::array<int, 3> FSession::SoundingVoices() const
	{
		std::array<int, 3> ByKind{};
		const FImpl& I = *Impl;
		if (!I.Sound)
		{
			return ByKind;
		}
		const FLockedGameSound Locked = I.Sound->Sound()->Lock();
		for (int32 Voice = 0; Voice < FSpu::VoiceCount; ++Voice)
		{
			// The voice's envelope level (its register 0Ch).
			constexpr uint32 LevelRegister = 0x0C;
			if (Locked.Spu().Read(static_cast<uint32>(Voice) * 16 + LevelRegister) != 0)
			{
				++ByKind[static_cast<std::size_t>(Locked.Driver().VoiceKind(Voice))];
			}
		}
		return ByKind;
	}

	FFrameInfo FSession::Info() const
	{
		FFrameInfo Info;
		const FImpl& I = *Impl;
		Info.HdUpload = I.HdUpload;
		Info.HdRect = I.HdRect;
		Info.HdSplit = I.HdSplit;
		Info.HdBeyond = I.HdBeyond;
		Info.SpriteBeyond = I.SpriteBeyond;
		Info.ScreenBeyond = I.ScreenBeyond;
		Info.KindsPlainDrawn = I.KindsPlainDrawn;
		Info.KindsRimDrawn = I.KindsRimDrawn;
		Info.KindsRimTexels = I.KindsRimTexels;
		Info.KindsRimScenery = I.KindsRimScenery;
		Info.BattleGlyphs = I.BattleGlyphs;
		Info.FromVram = I.FromVram;
		Info.MissNoUpload = I.MissNoUpload;
		Info.MissSplit = I.MissSplit;
		Info.MissName = I.MissName;
		Info.RectHitsByShift = I.RectHitsByShift;
		Info.PageHits = I.PageHits;
		Info.MapLoads = I.SceneGeneration;
		Info.SpritePieces = I.SpritePieces;
		Info.SpriteHd = I.SpriteHd;
		Info.SpritePartial = I.SpritePartial;
		Info.SpriteVram = I.SpriteVram;
		Info.SpriteNoUpload = I.SpriteNoUpload;
		Info.SpriteAllInPack = I.SpriteAllInPack;
		Info.SpriteSplitGaps = I.SpriteSplitGaps;
		Info.ScreenTextured = I.ScreenTextured;
		Info.ScreenHd = I.ScreenHd;
		Info.SpriteWaiting = I.SpriteWaiting;
		Info.ScreenWaiting = I.ScreenWaiting;
		Info.ScreenNoUpload = I.ScreenNoUpload;
		Info.ScreenAllInPack = I.ScreenAllInPack;
		Info.SceneryHd = I.SceneryHd;
		Info.SceneryVram = I.SceneryVram;
		Info.SceneryHdMixed = I.SceneryHdMixed;
		Info.SceneryLaid = I.SceneryLaid;
		Info.ScreenPrimitives = I.ScreenPrimitives;
		Info.ScreenHash = I.ScreenHash;
		Info.Waiting = I.Waiting;
		if (!I.Loop)
		{
			return Info;
		}
		Info.Program = static_cast<int>(I.Loop->Program());
		Info.Stage = static_cast<int>(I.Loop->Stage());
		if (I.Session)
		{
			Info.Story = I.Session->Game().SavedEventVariable(0);
		}
		Info.Screen = I.ScreenNow();
		const FScreenSize Size = FImpl::ScreenSizeOf(Info.Screen);
		Info.ScreenWidth = Size.Width;
		Info.ScreenHeight = Size.Height;
		if (const FMenuProgram* Menu = I.RunningMenu())
		{
			Info.MenuMode = static_cast<int>(I.Session->Kernel().MenuMode);
			Info.MenuNumber = Menu->Snapshot().Number;
			Info.MenuPrimitives = static_cast<int>(Menu->Snapshot().Primitives.size());
		}
		int View = -1;
		if (const FMoviePlayer* Player = I.PlayingMovie(View))
		{
			Info.MovieFrame = static_cast<int>(Player->FrameNumber());
			Info.MovieView = View;
		}
		Info.MoviePicture = I.MovieShown ? I.MovieRevision : 0;
		Info.MovieDisc = I.MovieShown ? I.MovieDisc : 0;
		Info.MovieNumber = I.MovieShown ? I.MovieNumber : -1;
		// The disc in the drive as the movie started, the one its sectors are read from (FGameSession::MovieDisc).
		Info.MovieSource = I.MovieShown ? I.IdOfDisc(I.MovieDisc - 1) : std::string();
		if (I.Session)
		{
			const int Drive = I.Session->DiscNumber();
			Info.DriveDisc = Drive + 1;
			Info.DriveDiscId = I.IdOfDisc(Drive);
			if (Drive == I.PlayedNumber)
			{
				Info.DriveDiscFile = !I.TranslationImage.empty() ? I.TranslationImage : I.Identity ? FImpl::Utf8Of(I.Library.FileOf(I.Identity->Release)) : std::string();
			}
			else if (Drive >= 0 && Drive < static_cast<int>(I.AddedDiscs.size()))
			{
				Info.DriveDiscFile = I.AddedDiscs[static_cast<std::size_t>(Drive)].File;
			}
		}
		Info.DiscsHeld = I.Session ? 1 << I.PlayedNumber : 0;
		for (std::size_t Number = 0; Number < I.AddedDiscs.size(); ++Number)
		{
			Info.DiscsHeld |= I.AddedDiscs[Number].Index ? 1 << Number : 0;
		}
		if (I.WantedDisc >= 0)
		{
			Info.DiscWanted = I.WantedDisc + 1;
			Info.DiscWantedKind = I.TranslationImage.empty() ? "usa" : "rus";
			const std::vector<std::filesystem::path> Folders = I.DiscFolders();
			Info.DiscWantedFolder = Folders.empty() ? std::string() : FImpl::Utf8Of(Folders[0]);
		}
		Info.MovieShownFrame = I.MovieShown ? static_cast<int>(I.MovieShownFrame) : 0;
		Info.MovieWidth = I.MovieShown ? I.MovieShown->Width : 0;
		Info.MovieHeight = I.MovieShown ? I.MovieShown->Height : 0;
		if (I.Session)
		{
			Info.CardLevel = I.Session->ChapterCardLine().empty() ? 0 : I.Session->ChapterCard().Level();
		}
		if (const FFieldProgram* Field = I.Field())
		{
			const FEventContext& Context = Field->Runtime().Context();
			Info.bField = true;
			Info.bPlayerControlled = Context.bPlayerControlled;
			Info.bMenuLocked = Context.bMenuLocked;
			if (const FFieldFrame* Latest = I.Frame())
			{
				Info.bCover = Latest->Cover.bShown;
				Info.bCoverScreen = Latest->Cover.bScreen;
				Info.CoverTaken = Latest->Cover.Taken;
				Info.ScreenInVram = static_cast<int>(Latest->ScreenInVram.size());
			}
			Info.Map = Context.RunningMap;
			Info.bRunning = Context.bFieldRunning;
			Info.Leader = Context.PartyActors[0];
			if (Info.Leader >= 0 && static_cast<std::size_t>(Info.Leader) < Context.Actors.size())
			{
				const auto& Position = Context.Actors[static_cast<std::size_t>(Info.Leader)].Position;
				Info.LeaderPosition = {Position[0], Position[1], Position[2]};
				// ActorSprite is the runtime's own non-const lookup; it only finds the sprite.
				if (const FSprite* Sprite = const_cast<FFieldSprites&>(Field->Runtime().Sprites()).ActorSprite(Info.Leader))
				{
					Info.LeaderFrame = Sprite->Frame;
				}
			}
			Info.bMessageOpen = std::any_of(Context.Messages.Windows.begin(), Context.Messages.Windows.end(),
				[](const FFieldMessageWindow& Window) { return Window.bOpen; });
			if (const FFieldFrame* Frame = I.Frame())
			{
				Info.bSceneDrawn = Frame->bSceneDrawn;
				Info.Tick = static_cast<int>(Frame->Tick);
				Info.Characters = static_cast<int>(Frame->Characters.size());
				Info.Background = {Frame->Background.R, Frame->Background.G, Frame->Background.B};
				Info.ProjectionDistance = static_cast<float>(std::max<uint16>(Frame->View.ProjectionDistance, 1));
			}
		}
		else if (const FWorldMapProgram* Map = I.WorldMap())
		{
			// The world map is drawn as the battle is: as the PS1 draws it, in its frame's order, no light of the port's.
			const FWorldMapContext& Context = Map->Runtime().Context();
			Info.bWorldMap = true;
			Info.bUnlit = true;
			Info.SceneLines = FImpl::WorldMapScreen.Height;
			Info.WorldScene = Context.SceneNumber;
			Info.TravelMode = Context.TravelMode;
			Info.MapPlace = Context.Place;
			Info.CameraYaw = Context.CameraYaw;
			Info.bPlayerControlled = Map->TicksMap() && Map->Runtime().CouldOpenMenu();
			// Where the party (or what it rides) stands, in whole units (the context keeps 20.12).
			Info.LeaderPosition = {Context.Controlled.X >> 12, Context.Controlled.Y >> 12, Context.Controlled.Z >> 12};
			Info.MapPolygons = I.MapPolygons;
			Info.MapOneSidedDropped = I.MapOneSidedDropped;
			Info.MapAnimatedPieces = I.MapAnimatedPieces;
			Info.MapAnimatedHd = I.MapAnimatedHd;
			Info.MapLayers = I.MapLayers;
			Info.FadeLevel = Map->ScreenFade().Picture == FWorldMapScreenFade::EPicture::None ? -1 : Map->ScreenFade().Level;
			if (Map->ScreenFade().Picture == FWorldMapScreenFade::EPicture::ScreenBefore)
			{
				// The display gives the picture it shows now under this key (main.gd, as for the field's picture of the screen).
				Info.CoverTaken = I.MapScreenBefore;
			}
			if (const FWorldMapFrame* Frame = Map->LatestFrame())
			{
				Info.bSceneDrawn = true;
				Info.Tick = static_cast<int>(Frame->Tick);
				Info.ProjectionDistance = static_cast<float>(std::max<int32>(Frame->ProjectionDistance, 1));
			}
		}
		else if (I.Battle() != nullptr)
		{
			// The battle is drawn as the PS1 draws it: no light of the port's, the game's own shadows.
			Info.bBattle = true;
			Info.bUnlit = true;
			if (I.Battle()->Runtime().IsInTransition())
			{
				Info.CoverTaken = I.BattleScreenBefore;
			}
			Info.ScreenWidth = MenuScreenSize.Width;
			Info.ScreenHeight = MenuScreenSize.Height;
			if (const FBattleShowFrame* Frame = I.BattleFrame())
			{
				Info.bSceneDrawn = Frame->bStageDrawn;
				Info.BattleStep = static_cast<int>(Frame->Step);
				Info.Tick = static_cast<int>(Frame->Step);
				Info.ProjectionDistance = static_cast<float>(std::max<int32>(Frame->ProjectionDistance, 1));
				if (Frame->bCleared)
				{
					Info.Background = {FilledChannel(Frame->ClearColor[0]), FilledChannel(Frame->ClearColor[1]), FilledChannel(Frame->ClearColor[2])};
				}
				const std::size_t Layer = FImpl::FirstLayer(*Frame);
				Info.SceneLinks = static_cast<int>(Layer);
				Info.OverLinks = static_cast<int>(Frame->Order.size() - Layer);
				Info.HudPrimitives = static_cast<int>(Frame->Hud.Primitives.size());
				// FNV-1a over what the HUD draws and where: a window opened, a cursor moved, a gauge filled.
				uint32 Hash = 2166136261u;
				const auto Mix = [&Hash](uint32 Value) {
					for (int Byte = 0; Byte < 4; ++Byte)
					{
						Hash = (Hash ^ (Value >> (Byte * 8) & 0xFF)) * 16777619u;
					}
				};
				for (const FMenuPrimitive& Primitive : Frame->Hud.Primitives)
				{
					Mix(Primitive.Code);
					for (const FMenuCorner& Corner : Primitive.Corners)
					{
						Mix(static_cast<uint16>(Corner.X) | static_cast<uint32>(static_cast<uint16>(Corner.Y)) << 16);
						Mix(Corner.U | Corner.V << 8);
					}
				}
				Info.HudHash = Hash;
			}
		}
		else if (const FBattlingGameProgram* Arena = I.Battling())
		{
			// The arena is drawn as the world map is: its frame in the same form, unlit, in its order, on its own 218 lines.
			const FBattlingFight& Fight = Arena->Fight();
			Info.bBattling = true;
			Info.bUnlit = true;
			Info.SceneLines = FImpl::BattlingScreen.Height;
			Info.ArenaStage = static_cast<int>(Arena->Stage());
			Info.ArenaState = Fight.State;
			Info.ArenaRound = Fight.Round;
			Info.ArenaWinner = Fight.Winner;
			Info.ArenaResult = Fight.Result;
			for (std::size_t Side = 0; Side < 2; ++Side)
			{
				const FBattlingFighter& Fighter = Fight.Fighters[Side];
				Info.ArenaGears[Side] = Arena->Gears()[Side];
				Info.ArenaHp[Side] = Fighter.Hp;
				Info.ArenaMaxHp[Side] = Fighter.MaxHp;
				Info.ArenaPositions[Side] = {Fighter.Position[0], Fighter.Position[1], Fighter.Position[2]};
			}
			if (const FBattlingFrame* Latest = Arena->LatestFrame())
			{
				Info.Tick = static_cast<int>(Latest->Pass);
				Info.ArenaColumns = Latest->Columns;
				Info.ArenaBlurs = Latest->PictureBlurs;
				Info.bArenaTrails = Latest->bTrails;
			}
			if (const FBattlingFrame* Shown = I.ArenaSceneFrame())
			{
				Info.bSceneDrawn = !Shown->Scene.Polygons.empty();
				Info.ProjectionDistance = static_cast<float>(std::max<int32>(Shown->Scene.ProjectionDistance, 1));
				// The clear colour as the GPU fills the screen with it (BattlingView.cpp, BattlingClearColor).
				Info.Background = {FilledChannel(Shown->Clear.R), FilledChannel(Shown->Clear.G), FilledChannel(Shown->Clear.B)};
			}
			Info.MapPolygons = I.MapPolygons;
			Info.MapOneSidedDropped = I.MapOneSidedDropped;
			Info.MapLayers = I.MapLayers;
		}
		return Info;
	}

	std::string FSession::DebugArena() const
	{
		const FImpl& I = *Impl;
		const FBattlingFrame* Shown = I.ArenaSceneFrame();
		if (Shown == nullptr)
		{
			return "no arena frame\n";
		}
		const FWorldMapFrame& Scene = Shown->Scene;
		const float Distance = static_cast<float>(std::max<int32>(Scene.ProjectionDistance, 1));
		const float Lines = static_cast<float>(FImpl::BattlingScreen.Height);
		const float ColumnScale = FImpl::ArenaColumnScale(*Shown);
		// As BeginMapDrawing places a point and main.gd's camera (fov from scene_lines) projects it onto the 320 x 218 screen.
		const float Across = (static_cast<float>(Scene.ScreenCenterX) * ColumnScale - 160.0f) / Distance;
		const float Lower = (static_cast<float>(Scene.ScreenCenterY) - Lines / 2.0f) / Distance;
		std::array<double, 11> Sum{}, Largest{}, SumX{}, SumY{};
		std::array<int, 11> Corners{}, Far{}, Saturated{};
		for (const FWorldMapPolygon& Polygon : Scene.Polygons)
		{
			// The sky's view corners reach past the screen's sides (its ScreenX keep the screen's corners): not compared.
			if (Polygon.Layer == EWorldMapLayer::Sky)
			{
				continue;
			}
			const std::size_t Layer = std::min<std::size_t>(static_cast<std::size_t>(Polygon.Layer), 10);
			for (std::size_t Corner = 0; Corner < Polygon.CornerCount && Corner < 4; ++Corner)
			{
				const std::array<float, 3>& View = Polygon.View[Corner];
				if (View[2] < 1.0f)
				{
					continue;
				}
				// The GTE saturates its screen coordinates at -1024..1023: a corner projected past them is not comparable.
				if (std::abs(Polygon.ScreenX[Corner]) >= 1023 || std::abs(Polygon.ScreenY[Corner]) >= 1023)
				{
					++Saturated[Layer];
					continue;
				}
				// Nearer than half the projection distance the GTE's divide saturates (its quotient capped at 2): its pixel is not the projection.
				if (View[2] * 2.0f < Distance)
				{
					++Saturated[Layer];
					continue;
				}
				const float X = 160.0f + (View[0] * ColumnScale + Across * View[2]) * Distance / View[2];
				const float Y = Lines / 2.0f + (View[1] + Lower * View[2]) * Distance / View[2];
				const double Dx = X - Polygon.ScreenX[Corner] * ColumnScale, Dy = Y - Polygon.ScreenY[Corner];
				const double Off = std::hypot(Dx, Dy);
				Sum[Layer] += Off;
				SumX[Layer] += Dx;
				SumY[Layer] += Dy;
				Far[Layer] += Off > 2.0 ? 1 : 0;
				Largest[Layer] = std::max(Largest[Layer], Off);
				++Corners[Layer];
			}
		}
		std::string Out;
		char Line[200];
		std::snprintf(Line, sizeof(Line), "arena frame: centre %d,%d distance %d columns %d polygons %zu\n", Scene.ScreenCenterX, Scene.ScreenCenterY, Scene.ProjectionDistance,
			Shown->Columns, Scene.Polygons.size());
		Out += Line;
		static constexpr std::array<const char*, 11> Names{"terrain", "sky", "horizon", "sprite", "model", "shadow", "tree", "cloud", "particle", "gear", "effect"};
		for (std::size_t Layer = 0; Layer < Names.size(); ++Layer)
		{
			if (Corners[Layer] > 0)
			{
				std::snprintf(Line, sizeof(Line), "  %s: %d corners (%d saturated), placed vs the GTE's pixel: mean %.3f (x %+.3f, y %+.3f), over 2 px %d, largest %.3f\n",
					Names[Layer], Corners[Layer], Saturated[Layer], Sum[Layer] / Corners[Layer], SumX[Layer] / Corners[Layer], SumY[Layer] / Corners[Layer], Far[Layer],
					Largest[Layer]);
				Out += Line;
			}
		}
		return Out;
	}

	std::string FSession::DebugBattle() const
	{
		const FImpl& I = *Impl;
		const FBattleGameProgram* Fight = I.Battle();
		if (Fight == nullptr)
		{
			return "no battle\n";
		}
		const FBattleShowFrame* Frame = I.BattleFrame();
		char Line[512];
		std::snprintf(Line, sizeof(Line), "battle: begun %d started %d paused %d fault %d in-transition %d\n", Fight->Presentation().HasBegun(),
			Fight->Presentation().Show.HasStarted(), Fight->Presentation().IsPaused(), static_cast<int>(Fight->Presentation().Fault()),
			Fight->Runtime().IsInTransition());
		std::string Out = Line;
		if (Frame == nullptr)
		{
			return Out;
		}
		std::array<int, 10> Kinds{};
		for (const FBattleShowLink& Link : Frame->Order)
		{
			++Kinds[std::min<std::size_t>(static_cast<std::size_t>(Link.Kind), Kinds.size() - 1)];
		}
		std::array<int, 4> ObjectKinds{};
		int Stage = 0;
		if (Frame->Objects != nullptr)
		{
			for (const FBattleObjectLink& Link : Frame->Objects->Links)
			{
				++ObjectKinds[static_cast<std::size_t>(Link.Kind) & 3];
				if (Link.Kind == EBattleObjectDraw::Polygon && Link.Index < Frame->Objects->Polygons.size())
				{
					Stage += Frame->Objects->Parts[Frame->Objects->Polygons[Link.Index].Part].Slot == FBattleObjects::StageSlot ? 1 : 0;
				}
			}
		}
		std::snprintf(Line, sizeof(Line),
			"frame step %u view distance %d centre %d,%d stage %d cleared %d clear %d,%d,%d vram rev %u\n"
			"order %zu: quad %d tri %d fade %d hud %d object %d backdrop %d tile %d line %d screenquad %d modelpoly %d; first layer at %zu\n"
			"objects links: polygon %d (stage %d) shadow %d cloth %d trail %d; backdrop dome packets %zu\n"
			"hud primitives %zu, fade mode %d colour %d,%d,%d\n",
			Frame->Step, Frame->ProjectionDistance, Frame->CentreX, Frame->CentreY, Frame->bStageDrawn, Frame->bCleared, Frame->ClearColor[0],
			Frame->ClearColor[1], Frame->ClearColor[2], Frame->VramRevision, Frame->Order.size(), Kinds[0], Kinds[1], Kinds[2], Kinds[3], Kinds[4],
			Kinds[5], Kinds[6], Kinds[7], Kinds[8], Kinds[9], FImpl::FirstLayer(*Frame), ObjectKinds[0], Stage, ObjectKinds[1], ObjectKinds[2],
			ObjectKinds[3], Frame->Backdrop.Dome.size(), Frame->Hud.Primitives.size(), Frame->Fade.Mode, Frame->Fade.Color[0], Frame->Fade.Color[1],
			Frame->Fade.Color[2]);
		Out += Line;
		std::array<int, 11> Drawers{};
		for (const FBattleShowQuad& Quad : Frame->Quads)
		{
			if (Quad.Drawer < Frame->Drawers.size())
			{
				++Drawers[std::min<std::size_t>(static_cast<std::size_t>(Frame->Drawers[Quad.Drawer].Kind), Drawers.size() - 1)];
			}
		}
		std::snprintf(Line, sizeof(Line), "quads by drawer: sprite %d shadow %d number %d totalburst %d total %d marker %d tile %d line %d trail %d model %d extension %d\n",
			Drawers[0], Drawers[1], Drawers[2], Drawers[3], Drawers[4], Drawers[5], Drawers[6], Drawers[7], Drawers[8], Drawers[9], Drawers[10]);
		Out += Line;
		// The order in runs of one kind: kind (Q quad, T triangle, F fade, H HUD, O object, B backdrop, t tile, l line, S screen quad, M model
		// polygon), its first and last table entry, how many.
		std::snprintf(Line, sizeof(Line), "polygons in front / clipped at the eye / behind it: scene %d %d %d, 2D layer %d %d %d\n", I.WorldBehind[0],
			I.WorldBehind[1], I.WorldBehind[2], I.ScreenBehind[0], I.ScreenBehind[1], I.ScreenBehind[2]);
		Out += Line;
		Out += "order runs:";
		static const char KindLetters[] = "QTFHOBtlSM";
		for (std::size_t Index = 0; Index < Frame->Order.size();)
		{
			std::size_t End = Index;
			while (End < Frame->Order.size() && Frame->Order[End].Kind == Frame->Order[Index].Kind)
			{
				++End;
			}
			std::snprintf(Line, sizeof(Line), " %c@%d..%d x%zu", KindLetters[std::min<std::size_t>(static_cast<std::size_t>(Frame->Order[Index].Kind), 9)],
				Frame->Order[Index].Entry, Frame->Order[End - 1].Entry, End - Index);
			Out += Line;
			Index = End;
		}
		Out += "\n";
		return Out;
	}

	std::string FSession::DebugCharacters() const
	{
		const FImpl& I = *Impl;
		const FFieldFrame* Frame = I.Field() != nullptr ? I.Frame() : nullptr;
		if (Frame == nullptr)
		{
			return "no field frame\n";
		}
		const FVram& Vram = I.Field()->Drawing().Vram();
		const FEventContext& Context = I.Field()->Runtime().Context();
		std::string Out;
		char Line[512];
		for (std::size_t Number = 0; Number < Frame->Characters.size(); ++Number)
		{
			const FFieldCharacterView& Character = Frame->Characters[Number];
			const uint32 Actor = Character.BlendKey >> 3;
			int Quads = 0, Opaque = 0, Texels = 0;
			uint32 Codes = 0;
			std::string First;
			for (const FFieldCharacterQuad& Quad : Frame->Quads)
			{
				if (Quad.Character != Number)
				{
					continue;
				}
				++Quads;
				Codes |= Quad.Quad.ColorCode;
				const FTexturePage Page = FTexturePage::FromPortAttribute(Quad.Quad.TexturePage);
				const FClutPosition Clut = FClutPosition::FromPortAttribute(Quad.Quad.Clut);
				const int Per = TexelsPerUnit(Page.Depth);
				for (int V = std::min(Quad.Quad.V0, Quad.Quad.V1); V < std::max(Quad.Quad.V0, Quad.Quad.V1); ++V)
				{
					for (int U = std::min(Quad.Quad.U0, Quad.Quad.U1); U < std::max(Quad.Quad.U0, Quad.Quad.U1); ++U)
					{
						const uint16 Unit = Vram.At(Page.X + U / Per, (Page.Y + V) & 1023);
						const int Index = Per == 4 ? (Unit >> ((U & 3) * 4)) & 15 : Per == 2 ? (Unit >> ((U & 1) * 8)) & 255 : -1;
						const uint16 Colour = Index < 0 ? Unit : Vram.At(Clut.X + Index, Clut.Y & 1023);
						++Texels;
						Opaque += Colour != 0 ? 1 : 0;
					}
				}
				if (First.empty())
				{
					char Text[160];
					std::snprintf(Text, sizeof(Text), "page %d,%d d%d clut %d,%d uv %d..%d,%d..%d colour %06x", Page.X, Page.Y, static_cast<int>(Page.Depth), Clut.X,
						Clut.Y, Quad.Quad.U0, Quad.Quad.U1, Quad.Quad.V0, Quad.Quad.V1, Quad.Quad.ColorCode & 0xFFFFFF);
					First = Text;
				}
			}
			uint32 Flags0 = 0, Flags1 = 0;
			if (const FEventActorState* State = Context.StateOf(static_cast<int32>(Actor)))
			{
				Flags0 = State->Flags0;
				Flags1 = State->Flags1;
			}
			std::snprintf(Line, sizeof(Line), "char %zu actor %u pass %u floor %d world (%d,%d,%d) clip %d quads %d codes %08x texels %d opaque %d flags0 %08x flags1 %08x | %s\n",
				Number, Actor, Character.BlendKey & 7, Character.bOnFloor, Character.World[0], Character.World[1], Character.World[2],
				static_cast<int>(Character.Clip), Quads, Codes, Texels, Opaque, Flags0, Flags1, First.c_str());
			Out += Line;
			// A shadow: where the painter's order puts it, and the scenery drawn after it over its centre (which hides it on the PS1).
			for (std::size_t QuadNumber = 0; Character.bOnFloor && QuadNumber < Frame->Quads.size(); ++QuadNumber)
			{
				if (Frame->Quads[QuadNumber].Character != Number)
				{
					continue;
				}
				std::size_t At = SIZE_MAX;
				for (std::size_t Entry = 0; Entry < Frame->Order.size(); ++Entry)
				{
					if (Frame->Order[Entry].Kind == EFieldDrawKind::Character && Frame->Order[Entry].Index == QuadNumber)
					{
						At = Entry;
					}
				}
				std::array<float, 3> Centre{};
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					const std::array<float, 3> Corner3 = Frame->Quads[QuadNumber].Quad.ViewCorner(Corner);
					for (std::size_t Axis = 0; Axis < 3; ++Axis)
					{
						Centre[Axis] += Corner3[Axis] / 4.0f;
					}
				}
				const float Distance = static_cast<float>(std::max<uint16>(Frame->View.ProjectionDistance, 1));
				const float Sx = FieldScreenCenterX + Centre[0] * Distance / std::max(Centre[2], 1.0f);
				const float Sy = FieldScreenCenterY + Centre[1] * Distance / std::max(Centre[2], 1.0f);
				const auto Inside = [&](const FFieldPolygonView& View, int A, int B, int C)
				{
					const auto Side = [&](int P, int Q)
					{
						return (View.ScreenX[Q] - View.ScreenX[P]) * (Sy - View.ScreenY[P]) - (View.ScreenY[Q] - View.ScreenY[P]) * (Sx - View.ScreenX[P]);
					};
					// A triangle the GPU draws: not flat, no corner at the GTE's saturated limits.
					for (const int Corner : {A, B, C})
					{
						if (View.ScreenX[Corner] <= -1024 || View.ScreenX[Corner] >= 1023 || View.ScreenY[Corner] <= -1024 || View.ScreenY[Corner] >= 1023)
						{
							return false;
						}
					}
					const float Area = static_cast<float>((View.ScreenX[B] - View.ScreenX[A]) * (View.ScreenY[C] - View.ScreenY[A])
						- (View.ScreenY[B] - View.ScreenY[A]) * (View.ScreenX[C] - View.ScreenX[A]));
					if (std::abs(Area) < 1.0f)
					{
						return false;
					}
					const float D0 = Side(A, B), D1 = Side(B, C), D2 = Side(C, A);
					return (D0 >= 0 && D1 >= 0 && D2 >= 0) || (D0 <= 0 && D1 <= 0 && D2 <= 0);
				};
				int Before = 0, After = 0;
				const FFieldScene& Scene = I.Field()->Drawing().Scene();
				for (std::size_t Entry = 0; Entry < Frame->Order.size(); ++Entry)
				{
					const FFieldDrawItem& Item = Frame->Order[Entry];
					if (Item.Kind != EFieldDrawKind::Scenery || Item.Index >= Frame->Scenery.Polygons.size())
					{
						continue;
					}
					const FFieldPolygonView& View = Frame->Scenery.Polygons[Item.Index];
					if (!View.bDrawn)
					{
						continue;
					}
					const FFieldScenePolygon& Polygon = Scene.Polygons[Item.Index];
					const bool bQuad = Scene.PartOf(Scene.Objects[Polygon.Object]).Primitives[Polygon.Primitive].Traits().Corners == 4;
					if (Inside(View, 0, 1, 2) || (bQuad && Inside(View, 1, 3, 2)))
					{
						(Entry < At ? Before : After) += 1;
						if (Entry > At && After <= 4)
						{
							std::snprintf(Line, sizeof(Line), "    after: order %zu polygon %u object %u bucket %u corners (%d,%d) (%d,%d) (%d,%d) (%d,%d)\n", Entry, Item.Index,
								Polygon.Object, View.Bucket, View.ScreenX[0], View.ScreenY[0], View.ScreenX[1], View.ScreenY[1], View.ScreenX[2], View.ScreenY[2],
								View.ScreenX[3], View.ScreenY[3]);
							Out += Line;
						}
					}
				}
				std::snprintf(Line, sizeof(Line), "  shadow quad %zu at order %zu of %zu, screen (%.0f,%.0f), view z %.0f; scenery over its centre: before %d, after %d\n",
					QuadNumber, At, Frame->Order.size(), Sx, Sy, Centre[2], Before, After);
				Out += Line;
			}
		}
		return Out;
	}

	std::string FSession::DebugMap() const
	{
		const FImpl& I = *Impl;
		const FWorldMapProgram* Map = I.WorldMap();
		const FWorldMapFrame* Frame = I.MapFrame();
		if (Map == nullptr || Frame == nullptr)
		{
			return "no world map frame\n";
		}
		const FVram& Vram = Map->Drawing().Vram();
		const auto Overlaps = [](const FVramRect& Rect, int X, int Y, int Wide, int High) {
			return Rect.X < X + Wide && X < Rect.X + Rect.Width && Rect.Y < Y + High && Y < Rect.Y + Rect.Height;
		};
		std::string Out;
		char Line[256];
		// The scene's place and notice records (whole units), for finding a way into a place.
		const FWorldMapScene& Scene = Map->Runtime().Scene();
		for (std::size_t List = 0; List < Scene.TriggerLists.size(); ++List)
		{
			if (!Scene.TriggerLists[List])
			{
				continue;
			}
			for (const FWorldMapTrigger& Record : *Scene.TriggerLists[List])
			{
				std::snprintf(Line, sizeof(Line), "record list %zu: x %d z %d %dx%d map %d scene %d name %d kind %d\n", List, Record.X, Record.Z, Record.Width,
					Record.Height, Record.Map, Record.Scene, Record.Name, Record.Kind);
				Out += Line;
			}
		}
		for (const FVramRect& Rect : I.MapAnimated)
		{
			std::snprintf(Line, sizeof(Line), "animated rect %d,%d %dx%d\n", Rect.X, Rect.Y, Rect.Width, Rect.Height);
			Out += Line;
		}
		// The textured polygons by layer and texture view: their page, CLUT, whether the page has pack pictures now and as
		// cached since the scene began, whether animations write into its texels or its CLUT's row.
		std::map<std::pair<int, uint32>, int> Views;
		for (const FWorldMapPolygon& Polygon : Frame->Polygons)
		{
			if (!Polygon.bTextured)
			{
				continue;
			}
			const FTexturePage Page = Polygon.bPortRows ? FTexturePage::FromPortAttribute(Polygon.TexturePage) : FTexturePage::FromAttribute(Polygon.TexturePage);
			const FClutPosition Clut = Polygon.bPortRows ? FClutPosition::FromPortAttribute(Polygon.Clut) : FClutPosition::FromAttribute(Polygon.Clut);
			++Views[{static_cast<int>(Polygon.Layer), PackTextureView(Page, Clut)}];
		}
		for (const auto& [Key, Count] : Views)
		{
			const uint32 View = Key.second;
			const FTextureRegion Whole = FImpl::WholePage(View);
			bool bNow = false;
			for (const FBeetleTexturePart& Part : BeetleTextureParts(Vram, Whole))
			{
				bNow = bNow || I.InPack(PackKey(Part.Upload, Part.Palette)) != nullptr || I.InPack(PackKey(Part.Upload, Part.ReducedPalette)) != nullptr;
			}
			const FTexturePage Page = TextureViewPage(View);
			const FClutPosition Clut = TextureViewClut(View);
			const int Units = 64 * (1 << static_cast<int>(Page.Depth));
			bool bTexelsAnimated = false, bClutAnimated = false;
			for (const FVramRect& Rect : I.MapAnimated)
			{
				bTexelsAnimated = bTexelsAnimated || Overlaps(Rect, Page.X, Page.Y, Units, 256);
				bClutAnimated = bClutAnimated || Overlaps(Rect, Clut.X, Clut.Y, Page.Depth == ETextureDepth::Indexed4 ? 16 : 256, 1);
			}
			std::snprintf(Line, sizeof(Line), "layer %d page %d,%d depth %d clut %d,%d: %d polygons, pictures now %d (or through an agreeing palette) %d, texels animated %d, clut animated %d\n",
				Key.first, Page.X, Page.Y, static_cast<int>(Page.Depth), Clut.X, Clut.Y, Count, bNow, static_cast<int>(const_cast<FImpl&>(I).PageState(Vram, View) != 0),
				bTexelsAnimated, bClutAnimated);
			Out += Line;
			if (std::getenv("XENO_MAP_PARTS") != nullptr && Count >= 100)
			{
				// The uploads under the page: where in it, their names, which palette's picture the pack has.
				for (const FBeetleTexturePart& Part : BeetleTextureParts(Vram, Whole))
				{
					// The indices the part's texels use, at or past 240 (the palettes' animated tail).
					std::string High;
					const int Per = TexelsPerUnit(Page.Depth);
					std::array<bool, 256> Used{};
					for (int V = Part.V; V < Part.V + Part.Height; ++V)
					{
						for (int U = Part.U; U < Part.U + Part.Width; ++U)
						{
							const uint16 Word = Vram.TexelAt(Page.X + U / Per, Page.Y + V);
							const int Index = Per == 2 ? (Word >> ((U & 1) * 8) & 255) : Per == 4 ? (Word >> ((U & 3) * 4) & 15) : 0;
							Used[static_cast<std::size_t>(Index)] = true;
						}
					}
					for (int Index = 240; Index < 256; ++Index)
					{
						High += Used[static_cast<std::size_t>(Index)] ? std::to_string(Index) + " " : "";
					}
					std::snprintf(Line, sizeof(Line), "    part u %d v %d %dx%d %08x-%08x %s / reduced %08x %s; uses %s\n", Part.U, Part.V, Part.Width, Part.Height,
						Part.Upload, Part.Palette, I.InPack(PackKey(Part.Upload, Part.Palette)) ? "IN" : "-", Part.ReducedPalette,
						I.InPack(PackKey(Part.Upload, Part.ReducedPalette)) ? "IN" : "-", High.c_str());
					Out += Line;
				}
			}
		}
		return Out;
	}

	const uint16_t* FSession::Vram() const
	{
		const FVram* Vram = Impl->SceneVram();
		return Vram != nullptr ? Vram->AllUnits().data() : nullptr;
	}

	int FSession::VramRows() const
	{
		return FVram::Rows;
	}

	void FSession::BuildWorld(std::vector<FSurface>& Out)
	{
		FImpl& I = *Impl;
		// For checks (Unhandled): the triangles of the scene that blend, however BuildWorld returns.
		struct FBlendedCount
		{
			const std::vector<FSurface>& Out;
			int& Blended;
			~FBlendedCount()
			{
				Blended = 0;
				for (const FSurface& Surface : Out)
				{
					Blended += Surface.Blend != EBlend::Opaque ? static_cast<int>(Surface.Mesh.Vertices() / 3) : 0;
				}
			}
		} BlendedCount{Out, I.WorldBlended};
		FCollector Into(Out, false);
		I.HdUpload = I.HdRect = I.HdSplit = I.FromVram = 0;
		I.HdBeyond = I.SpriteBeyond = I.KindsPlainDrawn = I.BattleGlyphs = I.KindsRimDrawn = I.KindsRimTexels = I.KindsRimScenery = 0;
		I.SpritePieces = I.SpriteHd = I.SpritePartial = I.SpriteVram = I.SpriteNoUpload = I.SpriteAllInPack = I.SpriteSplitGaps = 0;
		I.SpriteWaiting = 0;
		I.SceneryHd = I.SceneryVram = I.SceneryHdMixed = I.SceneryLaid = 0;
		I.Waiting = 0;
		I.FrameHits.clear();
		I.PageStates.clear();
		if (const FBattleShowFrame* Battle = I.BattleFrame())
		{
			// The links the GPU draws before the first layer (the fade or the HUD), each at its place in the order.
			I.FollowScene();
			I.BeginBattleDrawing(*Battle, false);
			const std::size_t Layer = FImpl::FirstLayer(*Battle);
			for (std::size_t Index = 0; Index < Layer; ++Index)
			{
				I.AddBattleLink(Into, *Battle, *Battle->Vram, Battle->Order[Index]);
			}
			I.EndBattleDrawing();
			return;
		}
		if (const FWorldMapProgram* Map = I.WorldMap())
		{
			// The map's latest frame: its own, under a fade of its latest frame, or standing still under the menu
			// (WorldMapView.cpp, Capture / CaptureStill); nothing during the fade of the screen before it (that picture is the 2D layer's).
			const FWorldMapFrame* Latest = Map->LatestFrame();
			if (Latest != nullptr && (I.RunningMenu() != nullptr || Map->ScreenFade().Picture != FWorldMapScreenFade::EPicture::ScreenBefore))
			{
				I.FollowScene();
				I.AddMapScene(Into, Map->Drawing().Vram(), *Latest);
			}
			return;
		}
		if (const FBattlingGameProgram* Arena = I.Battling())
		{
			// The arena's scene (BattlingView.cpp, Capture): the latest frame's, or a paused frame's picture; the menus' and
			// the versus screen's frames have none (their 2D layer over the clear colour).
			if (const FBattlingFrame* Shown = I.ArenaSceneFrame(); Shown != nullptr && !Shown->Scene.Polygons.empty())
			{
				I.FollowScene();
				I.AddMapScene(Into, Arena->Vram(), Shown->Scene, static_cast<float>(FImpl::BattlingScreen.Height), FImpl::ArenaColumnScale(*Shown));
			}
			return;
		}
		const FFieldProgram* Field = I.Field();
		const FFieldFrame* Frame = I.Frame();
		if (Frame == nullptr || !Frame->bSceneDrawn)
		{
			return;
		}
		// A movie full screen is drawn instead of the scene (FieldScreenFrame.cpp); the gear shop's menu draws no picture under it (MenuView.cpp).
		const EScreenKind ShownNow = I.ScreenNow();
		const FMenuProgram* Menu = I.RunningMenu();
		if (ShownNow == EScreenKind::FieldMovie || (ShownNow == EScreenKind::Menu && Menu != nullptr && Menu->GearModel() != nullptr))
		{
			return;
		}
		const FFieldScene& Scene = Field->Drawing().Scene();
		const FVram& Vram = Field->Drawing().Vram();
		const FFieldSceneFrame& Scenery = Frame->Scenery;
		if (Scenery.Polygons.size() != Scene.Polygons.size() || Scenery.Objects.size() != Scene.Objects.size())
		{
			return; // a frame of the map before (a map change): the scene is the new map's
		}
		I.FollowScene();
		if (Frame->Backdrop.bShown)
		{
			I.AddFieldBackdrop(Into, Vram, *Frame);
		}

		// The vertices MIMe animations moved this tick, by object.
		std::vector<const FFieldMovedModel*> Moved(Scene.Objects.size(), nullptr);
		for (const FFieldMovedModel& Model : Frame->MovedModels)
		{
			if (Model.Object < Moved.size())
			{
				Moved[Model.Object] = &Model;
			}
		}

		// For a frame report: each polygon's place in the GPU's order, and the polygons left undrawn by why.
		std::vector<int> OrderOf;
		std::array<float, 4> Depths{};
		if (I.Report != nullptr)
		{
			OrderOf.assign(Scene.Polygons.size(), -1);
			for (std::size_t Place = 0; Place < Scenery.DrawOrder.size(); ++Place)
			{
				if (Scenery.DrawOrder[Place] < OrderOf.size())
				{
					OrderOf[Scenery.DrawOrder[Place]] = static_cast<int>(Place);
				}
			}
			std::map<int, int> Undrawn;
			for (const FFieldPolygonView& View : Scenery.Polygons)
			{
				Undrawn[View.bDrawn ? -1 : View.Dropped] += 1;
			}
			I.Dump("field scene: %zu polygons, %zu objects, %zu in the GPU's order; drawn %d; undrawn by drop bits (1 model hidden or off screen, 4 off "
				"screen, 8 back face, 16 zero depth, 32 beyond the far bucket):", Scene.Polygons.size(), Scene.Objects.size(), Scenery.DrawOrder.size(),
				Undrawn.count(-1) != 0 ? Undrawn[-1] : 0);
			for (const auto& [Bits, Polygons] : Undrawn)
			{
				if (Bits >= 0)
				{
					I.Dump(" %d: %d", Bits, Polygons);
				}
			}
			I.Dump("\nThe PS1 draws the scene in the order above (far bucket first) without a depth buffer; the port draws the polygons drawn here "
				"two-sided through a depth buffer (z: view units, larger is farther).\n");
		}
		// Each drawn polygon's corners in view space (x right, y down, z forward, the eye at the origin).
		const auto PlaceCorners = [&](std::size_t Number, std::array<std::array<float, 3>, 4>& Out) -> uint32
		{
			const FFieldScenePolygon& Polygon = Scene.Polygons[Number];
			const FMdlPart& Part = Scene.PartOf(Scene.Objects[Polygon.Object]);
			const FMdlPrimitive& Primitive = Part.Primitives[Polygon.Primitive];
			const FAffine& Exact = Scenery.Objects[Polygon.Object].Exact;
			const FFieldMovedModel* MovedHere = Moved[Polygon.Object];
			const uint32 Count = Primitive.Traits().Corners;
			for (std::size_t Corner = 0; Corner < Count; ++Corner)
			{
				const uint16 Vertex = Primitive.Vertices[Corner];
				if (const FFieldSceneJoin* Join = Scene.JoinOf(Polygon.Object, Vertex))
				{
					Out[Corner] = Apply(Scenery.Objects[Join->Anchor].Exact, Join->Point[0], Join->Point[1], Join->Point[2]);
				}
				else
				{
					const FGteVector& Local = MovedHere != nullptr && Vertex < MovedHere->Count ? Frame->Vertices[MovedHere->First + Vertex]
						: Part.Vertices[Vertex];
					Out[Corner] = Apply(Exact, Local[0], Local[1], Local[2]);
				}
			}
			return Count;
		};
		std::vector<std::array<std::array<float, 3>, 4>> Placed(Scene.Polygons.size());
		std::vector<uint32> PlacedCount(Scene.Polygons.size(), 0);
		for (std::size_t Number = 0; Number < Scene.Polygons.size(); ++Number)
		{
			if (Scenery.Polygons[Number].bDrawn)
			{
				PlacedCount[Number] = PlaceCorners(Number, Placed[Number]);
			}
		}
		// The PS1 draws the scene in its order without a depth buffer: a polygon lying on one it drew before (a picture on a
		// wall, a rug on a floor, a sign on a door) covers it wholly. Through the depth buffer two such polygons fight (they
		// meet along a jagged line where their planes cross). So each drawn polygon that lies on an earlier one in the
		// frame's order is moved nearer the eye along its lines of sight (scaled toward the eye: the same pixels on the
		// screen), just past that one's plane (FieldLaying): the depth buffer then gives the PS1's order.
		std::vector<float> LaidScale(Scene.Polygons.size(), 1.0f);
		if (std::getenv("XENO_WITHOUT_LAYING") == nullptr)
		{
			LayScenery(Scenery.DrawOrder, Placed, PlacedCount, LaidScale);
		}
		for (std::size_t Number = 0; Number < Scene.Polygons.size(); ++Number)
		{
			const FFieldPolygonView& View = Scenery.Polygons[Number];
			if (!View.bDrawn)
			{
				continue;
			}
			const FFieldScenePolygon& Polygon = Scene.Polygons[Number];
			const FFieldSceneObject& Object = Scene.Objects[Polygon.Object];
			const FMdlPart& Part = Scene.PartOf(Object);
			const FMdlPrimitive& Primitive = Part.Primitives[Polygon.Primitive];
			const FMdlPrimitiveTraits& Traits = Primitive.Traits();

			FLook Look;
			const bool bSemi = (Polygon.Packet.Code & 2) != 0;
			const bool bRaw = (Polygon.Packet.Code & 1) != 0 && !View.bFogged;
			Look.Flags = (bRaw ? FlagRaw : 0.0f) + (bSemi ? FlagSemi : 0.0f);
			EBlend Blend = EBlend::Opaque;
			if (Traits.bTextured)
			{
				SetPage(Look, Polygon.Page, Polygon.Clut);
				Blend = bSemi ? BlendOf(Polygon.Page.Blend) : EBlend::Opaque;
			}
			else if (bSemi)
			{
				Blend = BlendOf(View.UntexturedBlend);
			}

			std::array<FCorner, 4> Corners{};
			const float Laid = LaidScale[Number];
			I.SceneryLaid += Laid < 1.0f ? 1 : 0;
			for (std::size_t Corner = 0; Corner < Traits.Corners; ++Corner)
			{
				const std::array<float, 3>& At = Placed[Number][Corner];
				Corners[Corner].Pos = ToGodot({At[0] * Laid, At[1] * Laid, At[2] * Laid});
				Corners[Corner].Color = ColorOf(View.Colors[Traits.bGouraud ? Corner : 0]);
				Corners[Corner].U = Primitive.Uvs[Corner].U;
				Corners[Corner].V = Primitive.Uvs[Corner].V;
				Depths[Corner] = At[2];
			}
			if (I.Report != nullptr)
			{
				I.Report->Who = "scenery object " + std::to_string(Polygon.Object);
			}
			I.PushScenery(Into, Vram, Corners, Traits.Corners, Look, Traits.bTextured, Polygon.Page, Polygon.Clut, Blend);
			if (I.Report != nullptr)
			{
				// A frame report's line per polygon: where the PS1 draws it (its place in the GPU's order, its ordering-table
				// bucket), its depth in view units at each corner, the drops the original's rules would make, its packet, its
				// texels, the path they took (the "object" line before it has its uploads).
				I.Dump("polygon %zu object %u primitive %u order %d of %zu bucket %u drop %u code %02x corners %u textured %d gouraud %d fogged %d blend %d",
					Number, static_cast<unsigned>(Polygon.Object), static_cast<unsigned>(Polygon.Primitive), OrderOf[Number], Scenery.DrawOrder.size(),
					static_cast<unsigned>(View.Bucket), static_cast<unsigned>(View.Dropped), static_cast<unsigned>(Polygon.Packet.Code),
					static_cast<unsigned>(Traits.Corners), Traits.bTextured ? 1 : 0, Traits.bGouraud ? 1 : 0, View.bFogged ? 1 : 0, static_cast<int>(Blend));
				if (Laid < 1.0f)
				{
					// Laid on a polygon drawn before it: its corners at this share of their distance from the eye.
					I.Dump(" laid %.5f", Laid);
				}
				if (Traits.bTextured)
				{
					I.Dump(" page %d,%d depth %d pageblend %d clut %d,%d", Polygon.Page.X, Polygon.Page.Y, static_cast<int>(Polygon.Page.Depth),
						static_cast<int>(Polygon.Page.Blend), Polygon.Clut.X, Polygon.Clut.Y);
				}
				I.Dump(" z");
				for (std::size_t Corner = 0; Corner < Traits.Corners; ++Corner)
				{
					I.Dump(" %.0f", Depths[Corner]);
				}
				I.Dump(" screen");
				for (std::size_t Corner = 0; Corner < Traits.Corners; ++Corner)
				{
					I.Dump(" (%d,%d uv %d,%d)", View.ScreenX[Corner], View.ScreenY[Corner], Primitive.Uvs[Corner].U, Primitive.Uvs[Corner].V);
				}
				I.Dump(" -> %s\n", I.DumpPath.c_str());
			}
		}

		// The characters' sprites and shadows: quads already in view space. A character's key is its actor << 3 and its pass
		// (FieldFrameCapture.cpp); soft shadows go only under actors drawn this frame, not under ones kept invisible.
		constexpr uint32 KeyShift = 3;
		std::vector<uint32> Shown;
		for (const FFieldCharacterView& Character : Frame->Characters)
		{
			if (!Character.bOnFloor)
			{
				Shown.push_back(Character.BlendKey >> KeyShift);
			}
		}
		// A sprite stands up facing the screen, so its lower rows reach under the floor its feet are on; the PS1 draws it after
		// the floor, here depth decides. Drawn 3 % nearer the camera along the line of sight, it stays where it is on screen;
		// each quad a hair nearer than the next, as the PS1 draws a sprite's first pieces over its later ones (their cells
		// overlap where a mirrored piece keeps its whole cell).
		const std::size_t QuadCount = Frame->Quads.size();
		for (std::size_t Number = 0; Number < QuadCount; ++Number)
		{
			const FFieldCharacterQuad& Character = Frame->Quads[Number];
			// XENO_ORDER=reverse flips which pieces lie on top, for comparisons.
			static const bool bReverse = std::getenv("XENO_ORDER") != nullptr;
			const float Nearer = 0.97f - 1e-5f * static_cast<float>(bReverse ? Number + 1 : QuadCount - Number);
			const bool bShadow = Character.Character < Frame->Characters.size() && Frame->Characters[Character.Character].bOnFloor;
			if (bShadow && !I.Options.bOriginalShadows)
			{
				continue;
			}
			if (bShadow && I.Options.bSoftShadows
				&& std::find(Shown.begin(), Shown.end(), Frame->Characters[Character.Character].BlendKey >> KeyShift) == Shown.end())
			{
				continue;
			}
			const FSpriteQuad& Quad = Character.Quad;
			const std::array<std::array<int16, 2>, 4> Texels{{{Quad.U0, Quad.V0}, {Quad.U1, Quad.V0}, {Quad.U0, Quad.V1}, {Quad.U1, Quad.V1}}};
			if (I.Report != nullptr)
			{
				I.Report->Who = Character.Character < Frame->Characters.size() ? I.SpriteWho(*Field, Frame->Characters[Character.Character]) : "a character";
				I.DumpPath = "from VRAM (shadow)";
			}
			I.PushViewQuad(Into, Vram, Quad.Matrix, Quad.Corners, Texels, Quad.TexturePage, Quad.Clut, true, Quad.ColorCode & 0xFFFFFF,
				(Quad.ColorCode >> 24 & 1) != 0, (Quad.ColorCode >> 25 & 1) != 0, !bShadow, !bShadow, bShadow ? 1.0f : Nearer);
			if (I.Report != nullptr)
			{
				// A frame report's line per sprite piece (as XENO_DUMP_2D's battle quads): whose, its texels, the path they took.
				const FTexturePage Page = FTexturePage::FromPortAttribute(Quad.TexturePage);
				const FClutPosition Clut = FClutPosition::FromPortAttribute(Quad.Clut);
				I.Dump("piece %zu %s%s code %08x page %d,%d depth %d pageblend %d clut %d,%d uv %d,%d-%d,%d cell v %d-%d corners", Number, I.Report->Who.c_str(),
					bShadow ? " shadow" : "", Quad.ColorCode, Page.X, Page.Y, static_cast<int>(Page.Depth), static_cast<int>(Page.Blend), Clut.X, Clut.Y, Quad.U0,
					Quad.V0, Quad.U1, Quad.V1, Quad.CellV0, Quad.CellV1);
				for (std::size_t Corner = 0; Corner < 4; ++Corner)
				{
					const std::array<float, 3> At = ViewPoint(Quad.Matrix, Quad.Corners[Corner]);
					I.Dump(" (%g,%g,%g)", At[0], At[1], At[2]);
				}
				I.Dump(" -> %s\n", I.DumpPath.c_str());
			}
		}
		if (I.Report != nullptr)
		{
			I.Report->Who = "a field particle";
		}
		for (const FFieldParticleQuad& Particle : Frame->Particles)
		{
			const uint32 Color = Particle.Color[0] | Particle.Color[1] << 8 | static_cast<uint32>(Particle.Color[2]) << 16;
			I.PushViewQuad(Into, Vram, Particle.Matrix, Particle.Corners, Particle.Texels, Particle.TexturePage, Particle.Clut, false, Color, false, true,
				false);
		}
		// What the GPU draws besides: the gears' models and the sprites' children's models (FFieldFrame::Order's Gear and SpriteModel entries).
		if (!FImpl::WithoutTask7())
		{
			I.AddFieldGears(Into, Vram, *Frame);
			I.AddFieldSpriteModels(Into, Vram, *Frame);
		}
	}

	void FSession::BuildScreen(std::vector<FSurface>& Out)
	{
		FImpl& I = *Impl;
		FCollector Into(Out, true);
		I.ScreenTextured = I.ScreenHd = I.ScreenNoUpload = I.ScreenAllInPack = 0;
		I.ScreenWaiting = 0;
		I.ScreenBeyond = 0;
		I.ScreenPrimitives = 0;
		I.ScreenHash = 2166136261u;
		I.bCardDrawn = false;
		const EScreenKind Shown = I.ScreenNow();
		if (Shown == EScreenKind::Notice)
		{
			// The kernel's notice: its sprites over its own VRAM on a 320 x 240 screen (FBootNotice::DrawList).
			const FBootNotice& Notice = *I.Loop->Notice();
			Notice.DrawList(I.NoticeList);
			Into.Vram = EVramSource::ScreenVram;
			I.PushDrawList(Into, Notice.Vram(), I.NoticeList);
			return;
		}
		if (Shown == EScreenKind::Movie)
		{
			// The Movie program's window: the picture's top 216 lines, 10 lines down a 320 x 240 screen (MovieScreen.h).
			I.PushMovie(Into, {0, 10, 320, 216});
			return;
		}
		if (const FBattleGameProgram* Fight = I.Battle(); Fight != nullptr && !FImpl::WithoutTask7() && I.PushBattleTransition(Into, *Fight))
		{
			return;
		}
		if (const FBattleShowFrame* Battle = I.BattleFrame())
		{
			// What the GPU draws from the first layer on, in the order's sequence: the fade, the HUD, and the links between
			// and after them (numbers over the fade) projected onto the 2D layer.
			const FVram& Vram = *Battle->Vram;
			I.BeginBattleDrawing(*Battle, true);
			for (std::size_t Index = FImpl::FirstLayer(*Battle); Index < Battle->Order.size(); ++Index)
			{
				const FBattleShowLink& Link = Battle->Order[Index];
				if (Link.Kind == EBattleShowLink::Fade)
				{
					I.PushBattleFade(Into, *Battle);
				}
				else if (Link.Kind == EBattleShowLink::Hud)
				{
					I.PushBattleHud(Into, *Battle, Vram);
				}
				else
				{
					I.AddBattleLink(Into, *Battle, Vram, Link);
				}
			}
			I.EndBattleDrawing();
			return;
		}
		if (const FWorldMapProgram* Map = I.WorldMap())
		{
			// As WorldMapView.cpp and GameLoopScreen.cpp show the program: a menu over the map's latest frame standing still
			// (its lists fitted to the menu's 224 lines); the fade of the screen before over that picture; the map's frame
			// with its minimap, windows and fade, under a fade of its own frame; a chapter's card over it.
			const FVram& Vram = Map->Drawing().Vram();
			const FWorldMapFrame* Latest = Map->LatestFrame();
			const FWorldMapScreenFade& Fade = Map->ScreenFade();
			if (const FMenuProgram* Menu = I.RunningMenu())
			{
				if (Latest != nullptr)
				{
					I.ListScale = static_cast<float>(MenuScreenSize.Height) / FImpl::WorldMapScreen.Height;
					I.PushMapLayers(Into, Vram, *Latest);
					I.ListScale = 1.0f;
				}
				I.PushMenu(Into, *Menu);
				return;
			}
			if (Fade.Picture == FWorldMapScreenFade::EPicture::ScreenBefore)
			{
				if (I.PushMapScreenBefore(Into) && Fade.Level >= 0)
				{
					I.PushMapDarkening(Into, Fade.Level, Fade.Blend);
				}
				return;
			}
			if (Latest != nullptr)
			{
				I.PushMapLayers(Into, Vram, *Latest);
				if (Fade.Picture == FWorldMapScreenFade::EPicture::LatestFrame && Fade.Level >= 0)
				{
					I.PushMapDarkening(Into, Fade.Level, Fade.Blend);
				}
			}
			I.ListScale = static_cast<float>(FImpl::WorldMapScreen.Height) / ChapterCardScreen.Height;
			I.PushChapterCard(Into);
			I.ListScale = 1.0f;
			return;
		}
		if (const FBattlingGameProgram* Arena = I.Battling())
		{
			// The arena's 2D layer (BattlingView.cpp, AddPasses): a paused frame's over the picture the pause captured (that
			// picture's own layer under it), else the latest frame's: the labels and the HUD over the scene, or the menus' and
			// the versus screen's over the fire.
			const FBattlingFrame* Latest = Arena->LatestFrame();
			if (Latest == nullptr)
			{
				return;
			}
			const FBattlingFrame* Shown = I.ArenaSceneFrame();
			if (Shown != nullptr && Shown != Latest)
			{
				I.PushArenaLayer(Into, Arena->Vram(), *Shown);
			}
			I.PushArenaLayer(Into, Arena->Vram(), *Latest);
			return;
		}
		const FFieldProgram* Field = I.Field();
		const FFieldFrame* Frame = I.Frame();
		if (Frame == nullptr)
		{
			return;
		}
		const FVram& Vram = Field->Drawing().Vram();
		if (Shown == EScreenKind::FieldMovie)
		{
			// The field's movie fills its 320 x 224 screen; over the field, the message windows as the frame drew them (FieldView.cpp, Fill).
			I.PushMovie(Into, {0, 0, static_cast<int16>(MenuScreenSize.Width), static_cast<int16>(MenuScreenSize.Height)});
			if (I.bMovieOverField)
			{
				I.PushDrawList(Into, Vram, Frame->Screen);
			}
			return;
		}
		if (Shown == EScreenKind::Menu)
		{
			// The menu over the field's last picture standing still: its 2D layer without the menu's shade (the menu shades it
			// itself), the picture of the screen at its place, then the menu's list (FieldView.cpp CaptureStill, MenuView.cpp).
			const FMenuProgram& Menu = *I.RunningMenu();
			if (Menu.GearModel() == nullptr)
			{
				I.PushFieldLayer(Into, Vram, *Frame, 0, FFieldMenuShade::BlendKey);
			}
			I.PushMenu(Into, Menu);
			return;
		}
		I.PushFieldLayer(Into, Vram, *Frame, 0, 0);
		I.PushChapterCard(Into);
	}

	const uint16_t* FSession::VramOf(int Source)
	{
		FImpl& I = *Impl;
		if (Source == ScreenVram)
		{
			if (const FMenuProgram* Menu = I.RunningMenu(); Menu != nullptr && (I.Field() != nullptr || I.WorldMap() != nullptr))
			{
				return Menu->Vram().AllUnits().data();
			}
			if (I.Loop && I.Loop->Stage() == EGameLoopStage::Boot && I.Loop->Notice() != nullptr)
			{
				return I.Loop->Notice()->Vram().AllUnits().data();
			}
			return nullptr;
		}
		if (Source == OverlayVram)
		{
			return I.bCardDrawn ? I.CardDrawing.Pictures().AllUnits().data() : nullptr;
		}
		const FVram* Scene = I.SceneVram();
		if (Scene == nullptr)
		{
			return nullptr;
		}
		const FFieldFrame* Frame = I.Field() != nullptr ? I.Frame() : nullptr;
		return Frame != nullptr && !Frame->ScreenInVram.empty() ? I.PatchScreenInVram(*Scene, *Frame) : Scene->AllUnits().data();
	}

	uint64_t FSession::VramStamp(int Source) const
	{
		const FImpl& I = *Impl;
		const FVram* Vram = nullptr;
		uint64_t Extra = 0;
		if (Source == ScreenVram)
		{
			if (const FMenuProgram* Menu = I.RunningMenu(); Menu != nullptr && (I.Field() != nullptr || I.WorldMap() != nullptr))
			{
				Vram = &Menu->Vram();
			}
			else if (I.Loop && I.Loop->Stage() == EGameLoopStage::Boot && I.Loop->Notice() != nullptr)
			{
				Vram = &I.Loop->Notice()->Vram();
			}
		}
		else if (Source == OverlayVram)
		{
			Vram = I.bCardDrawn ? &I.CardDrawing.Pictures() : nullptr;
		}
		else
		{
			Vram = I.SceneVram();
			const FFieldFrame* Frame = I.Field() != nullptr ? I.Frame() : nullptr;
			if (Frame != nullptr && !Frame->ScreenInVram.empty())
			{
				Extra = I.ScreenInVramStamp(*Frame);
			}
		}
		if (Vram == nullptr)
		{
			return 0;
		}
		// Which VRAM (its address too: a menu's or a notice's own lineage may start over) and how many uploads it has taken.
		return ((static_cast<uint64_t>(Vram->Lineage()) << 32 | Vram->Revision()) ^ reinterpret_cast<uintptr_t>(Vram) * 31) ^ Extra;
	}

	void FSession::SetScreenPicture(int Taken, const uint8_t* Rgba, int Width, int Height)
	{
		FImpl& I = *Impl;
		if (Rgba == nullptr || Width <= 0 || Height <= 0)
		{
			return;
		}
		// The game screen in the window as the 2D layer places it: scaled to the window's height, centred across.
		std::vector<uint16>& Units = I.ScreenPictures[Taken];
		Units.assign(static_cast<std::size_t>(MenuScreenSize.Width) * MenuScreenSize.Height, 0);
		const double Scale = static_cast<double>(Height) / MenuScreenSize.Height;
		for (int Y = 0; Y < MenuScreenSize.Height; ++Y)
		{
			const int FromY = std::clamp(static_cast<int>((Y + 0.5) * Scale), 0, Height - 1);
			for (int X = 0; X < MenuScreenSize.Width; ++X)
			{
				const int FromX = std::clamp(static_cast<int>(Width * 0.5 + (X + 0.5 - MenuScreenSize.Width * 0.5) * Scale), 0, Width - 1);
				const uint8_t* Pixel = &Rgba[(static_cast<std::size_t>(FromY) * Width + FromX) * 4];
				Units[static_cast<std::size_t>(Y * MenuScreenSize.Width + X)] = static_cast<uint16>(Pixel[0] >> 3 | (Pixel[1] >> 3) << 5 | (Pixel[2] >> 3) << 10);
			}
		}
		// Only the pictures still held in VRAM, and the newest, are kept.
		const FFieldFrame* Frame = I.Field() != nullptr ? I.Frame() : nullptr;
		for (auto Kept = I.ScreenPictures.begin(); Kept != I.ScreenPictures.end();)
		{
			const int Key = Kept->first;
			const bool bHeld = Frame != nullptr
				&& std::any_of(Frame->ScreenInVram.begin(), Frame->ScreenInVram.end(), [Key](const FFieldScreenInVram& Region) { return Region.Taken == Key; });
			Kept = Key == Taken || bHeld ? std::next(Kept) : I.ScreenPictures.erase(Kept);
		}
		I.PatchedStamp = 0;
		++I.PicturesGiven;
		I.PictureWidth = Width;
		I.PictureHeight = Height;
	}

	bool FSession::MovieImage(std::vector<uint8_t>& Rgba, int& Width, int& Height) const
	{
		const FImpl& I = *Impl;
		if (!I.MovieShown || I.MovieShown->Width <= 0 || I.MovieShown->Height <= 0)
		{
			return false;
		}
		Width = I.MovieShown->Width;
		Height = I.MovieShown->Height;
		// As the MDEC converts it (BT.601, each chroma sample over 2 x 2 pixels, saturated).
		const std::vector<uint8> Rgb = ToRgb24(*I.MovieShown);
		Rgba.resize(static_cast<std::size_t>(Width) * Height * 4);
		for (std::size_t Pixel = 0; Pixel < static_cast<std::size_t>(Width) * Height && Pixel * 3 + 2 < Rgb.size(); ++Pixel)
		{
			Rgba[Pixel * 4] = Rgb[Pixel * 3];
			Rgba[Pixel * 4 + 1] = Rgb[Pixel * 3 + 1];
			Rgba[Pixel * 4 + 2] = Rgb[Pixel * 3 + 2];
			Rgba[Pixel * 4 + 3] = 255;
		}
		return true;
	}

	std::string FSession::DebugPlacements(int Count) const
	{
		std::string Out = Impl->MissLog;
		const FFieldFrame* Frame = Impl->Frame();
		if (Frame == nullptr)
		{
			return Out;
		}
		const FFieldScene& Scene = Impl->Field()->Drawing().Scene();
		const FAffine View = FAffine::From(Frame->View.View);
		char Line[256];
		for (std::size_t Object = 0; Object < Scene.Objects.size() && static_cast<int>(Object) < Count; ++Object)
		{
			const auto& Own = Frame->Scenery.Objects[Object].Exact.T;
			const auto& World = Frame->SceneryWorld[Object];
			const auto Through = Apply(View, static_cast<float>(World[0]), static_cast<float>(World[1]), static_cast<float>(World[2]));
			std::snprintf(Line, sizeof(Line), "obj %2zu model %2u actor %3u world (%6d %6d %6d) exact.T (%8.0f %8.0f %8.0f) view*world (%8.0f %8.0f %8.0f)\n",
				Object, Scene.Objects[Object].Model, Scene.Objects[Object].Actor, World[0], World[1], World[2], Own[0], Own[1], Own[2], Through[0],
				Through[1], Through[2]);
			Out += Line;
		}
		return Out;
	}

	std::array<float, 12> FSession::ViewTransform() const
	{
		std::array<float, 12> Out{1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0};
		const FFieldFrame* Frame = Impl->Frame();
		const FBattleShowFrame* Battle = Impl->BattleFrame();
		if (Frame == nullptr && Battle == nullptr)
		{
			return Out;
		}
		const FAffine View = Frame == nullptr ? FAffine::From(Battle->View) : Frame->bUnrounded ? Frame->UnroundedView : FAffine::From(Frame->View.View);
		// Godot = F * View with F = diag(1, -1, -1); the world keeps its own axes (y down) under it.
		const float Flip[3] = {1.0f, -1.0f, -1.0f};
		for (std::size_t Row = 0; Row < 3; ++Row)
		{
			for (std::size_t Column = 0; Column < 3; ++Column)
			{
				Out[Row * 3 + Column] = Flip[Row] * View.M[Row][Column] * ViewScale;
			}
			Out[9 + Row] = Flip[Row] * View.T[Row] * ViewScale;
		}
		return Out;
	}

	// The cheat panel. Every change goes through the game's own state (FGameState's typed members, the core's layout of its
	// records) and, where the game has one, its own routine; nothing is written that the game would not write itself.

	namespace
	{
		/** The name tables of the inventory's lists (as the menus name them: MenuShopList.cpp, MenuMainEquipList.cpp, MenuGearShopGoods.cpp). */
		constexpr std::array<int32, FGameState::InventoryListCount> ItemNameTables{22, 23, 17, 51, 50};
		/** The story flags' bit 15 (BattleResult.cpp, NormalExpRules): a member takes its share of EXP whole in both pools. */
		constexpr uint16 NormalExpRules = 0x8000;
		/** The most gold the game keeps (the field's AddGold, the battle's rewards). */
		constexpr uint32 MostGold = 9999999;
		/** The most of an item a slot holds (the field's GiveItem). */
		constexpr int MostOfAnItem = 99;
		constexpr uint8 MostLevel = 99;
		/** A combatant's status bit the battle's damage sets as it fells it (BattleResults.cpp, ApplyBattleResults). */
		constexpr uint16 KnockedOutStatus = 0x8000;
		/** The battle's share of a member's EXP between the pools, as the battle sets it for every member (BattlePartyStart.cpp, InitMember). */
		constexpr uint8 MemberExpShare = 5;
		constexpr uint8 NoGear = 0xFF;

		std::string Lowered(std::string Text)
		{
			for (char& C : Text)
			{
				C = static_cast<char>(std::tolower(static_cast<unsigned char>(C)));
			}
			return Text;
		}

		/** Codes of the game's text (a name table's entry, a name in the state) as text, its end code and what follows dropped. */
		std::string TextOf(std::span<const uint8> Codes)
		{
			std::string Text = MesTextOfCodes(Codes);
			while (!Text.empty() && (Text.back() == ' ' || Text.back() == '\n'))
			{
				Text.pop_back();
			}
			return Text;
		}

		/**
		 * A character's record as the battle reads it (FBattleCombatant::FromRecord over the record and its gear's, as a
		 * combatant's record is laid out: the character's 0xA4 bytes, then the gear's).
		 */
		FBattleCombatant CombatantOf(const FGameState& State, uint8 Character)
		{
			static_assert(GameStateLayout::CharacterSize == FBattleCombatant::CharacterRecordSize);
			std::array<uint8, FBattleCombatant::RecordSize> Record{};
			const std::span<const uint8> Block = State.Block();
			const std::size_t At = GameStateLayout::CharacterOffset(Character);
			std::copy_n(Block.begin() + static_cast<std::ptrdiff_t>(At), GameStateLayout::CharacterSize, Record.begin());
			const uint8 Gear = Record[GameStateLayout::Character::Gear];
			if (Gear < GameStateLayout::GearCount)
			{
				const std::size_t GearAt = GameStateLayout::GearOffset(Gear);
				std::copy_n(Block.begin() + static_cast<std::ptrdiff_t>(GearAt), GameStateLayout::GearSize, Record.begin() + FBattleCombatant::CharacterRecordSize);
			}
			return FBattleCombatant::FromRecord(Record);
		}

		/**
		 * EXP given as a won battle gives it, by the game's own routine (GiveBattleRewards, BattleResult.cpp): a battle of the
		 * members (NoCharacter for an empty slot) with one enemy felled that was worth Total. The routine does the rest as
		 * every won battle: the members share it (each its share in both pools under the normal rules, else half in each),
		 * every other character takes a reserve's three quarters of a third, the levels gained grow the stats by the disc's
		 * growth table, the skills a battle learns by level are learned, the AP per turn rises, the members' HP and EP are
		 * written back. The battle's context is one of no battle, holding what the routine reads: the members as their records
		 * are (no gear: the write-back of a gear's HP and fuel is left out), the rules' options of the player's settings, the
		 * rewards at the original's rate, random draws of a generator of its own (the game's own sequence is left as it was).
		 */
		std::string GiveExpAsBattle(FGameSession& Session, const std::array<uint8, FBattleContext::PartySlotCount>& Members, uint32 Total)
		{
			FGameState& State = Session.Game();
			const std::unique_ptr<FBattleContext> Context = std::make_unique<FBattleContext>();
			FPsxRandom Random(State.PlayTime() * 0x9E3779B9u + Total);
			Context->GameState = &State;
			Context->Random = &Random;
			Context->RuleOptions = Session.Settings().Fixes.BattleRules;
			uint8 First = FBattleContext::NoCharacter;
			for (const uint8 Character : Members)
			{
				First = First == FBattleContext::NoCharacter && Character < FGameState::CharacterCount ? Character : First;
			}
			if (First == FBattleContext::NoCharacter)
			{
				return "nobody to give EXP to";
			}
			for (std::size_t Slot = 0; Slot < Members.size(); ++Slot)
			{
				FBattleCombatant& Member = Context->Combatants[Slot];
				const uint8 Character = Members[Slot];
				if (Character >= FGameState::CharacterCount)
				{
					// An empty slot: as felled, so nothing is learned for it; its character (read by the Infinity attacks' levels) the first member's.
					Member.Character = First;
					Member.Status = KnockedOutStatus;
					continue;
				}
				Member = CombatantOf(State, Character);
				Member.Character = Character;
				Member.Status = 0;
				Member.BattleFlags = 0;
				Member.Gear = NoGear;
				Member.ExpShare = MemberExpShare;
				Member.EtherExpShare = MemberExpShare;
				Context->PartyCharacters[Slot] = Character;
				Context->InBattle[Slot] = true;
			}
			FBattleCombatant& Foe = Context->Combatants[FBattleContext::PartySlotCount];
			Foe.Status = KnockedOutStatus;
			Foe.ExpReward = Total;
			Context->InBattle[FBattleContext::PartySlotCount] = true;
			GiveBattleRewards(*Context, Session.BattleFiles().Growth);
			return Context->Fault == EBattleFault::None ? std::string{} : "the battle's result faulted";
		}

		/** The battle's end teaches Chu-Chu and Maria no Deathblows (BattleResult.cpp, LearnSkills: "Id > Maria || Id < ChuChu"). */
		constexpr uint8 ChuChuCharacter = 7;
		constexpr uint8 MariaCharacter = 8;
		/** A Deathblow's 7 thresholds (one a basic-attack counter) and its level in the growth table (BattleResult.cpp, Growth). */
		constexpr int DeathblowCounterCount = 7;
		constexpr std::size_t DeathblowLevelsAt = 0x100;
		/** The story flags' bit 14: the 7-AP tier open (BattleResult.cpp, LateTier). */
		constexpr uint16 UpperTierOpen = 0x4000;

		uint16 SkillsWord(const FGameState& State, uint8 Character, std::size_t Field)
		{
			return LittleEndian::ReadU16(State.Block(), GameStateLayout::LearnedSkillsOffsetOf(Character) + Field);
		}

		/** A character's Deathblows as the Skills screen lists them: every number its name table names (MenuMainSkills.cpp, DrawDeathblows). */
		std::vector<FCheatDeathblow> DeathblowsOf(const FGameSession& Session, uint8 Character)
		{
			std::vector<FCheatDeathblow> Out;
			const FGameState& State = Session.Game();
			const std::span<const uint8> Growth = Session.BattleFiles().Growth.Bytes();
			const std::size_t Record = static_cast<std::size_t>(Character) * CharacterSkills::GrowthRecordSize;
			for (int Number = 0; Number < CharacterSkills::DeathblowCount; ++Number)
			{
				FCheatDeathblow Deathblow;
				Deathblow.Number = Number;
				Deathblow.Name = TextOf(Session.Text().NameTables.String(Character, Number));
				if (Deathblow.Name.empty())
				{
					continue;
				}
				Deathblow.bLearned = IsDeathblowLearned(State, Character, Number);
				const std::size_t LevelAt = Record + DeathblowLevelsAt + static_cast<std::size_t>(Number);
				Deathblow.Level = LevelAt < Growth.size() ? Growth[LevelAt] : 0;
				Deathblow.Percent = static_cast<int>(DeathblowPercent(State, Character, Number, Growth));
				Deathblow.bUpperTier = Number >= CharacterSkills::FirstUpperTier;
				Deathblow.bTierOpen = !Deathblow.bUpperTier || (State.StoryFlags() & UpperTierOpen) != 0;
				// The pattern whose Fierce press finishes it (BattlePartyAttack.cpp, MatchPattern / PatternDeathblow): 0 Fierce, 2 Weak, 3 Strong.
				const FBattleProgramTables& Program = Session.BattleFiles().Program;
				for (int Pattern = 0; Pattern < FBattleProgramTables::PatternCount && Character < FBattleProgramTables::DeathblowListCount; ++Pattern)
				{
					if (Program.Deathblows[Character][static_cast<std::size_t>(Pattern)] != Number)
					{
						continue;
					}
					for (const uint8 Press : Program.Patterns[static_cast<std::size_t>(Pattern)])
					{
						Deathblow.Buttons += Press == 0 ? "F" : Press == 2 ? "W" : Press == 3 ? "S" : "";
					}
					Deathblow.Buttons += "F";
					break;
				}
				Out.push_back(std::move(Deathblow));
			}
			return Out;
		}

		/**
		 * Every Deathblow the battle's end would teach the character now, by the game's own routine (GiveBattleRewards ->
		 * LearnSkills -> LearnDeathblow, BattleResult.cpp), as if the character had practised each of its basic attacks as far as
		 * the growth table asks: the character stands in a party slot of a battle won against nobody, its counters raised to
		 * the highest threshold of its Deathblows. The routine learns one Deathblow a battle (the first not yet learned whose
		 * level and thresholds are reached; none past the first whose level is too high; the 7-AP tier only once the story
		 * opens it), so the battle is repeated until it learns no more. With it come what that end works out from the learned
		 * skills: the gear Deathblows they unlock, the first ability the level reaches, the AP per turn a step. The character is
		 * in no party slot of the battle's own (its EXP is a reserve's share of nothing, 0; its record is not written back), so its
		 * EXP, HP, EP and practice counters are left as they are. Returns how many it learned.
		 */
		int LearnDeathblowsAsBattle(FGameSession& Session, uint8 Character, std::string& Error)
		{
			FGameState& State = Session.Game();
			const std::span<const uint8> Growth = Session.BattleFiles().Growth.Bytes();
			FBattleCombatant Practised = CombatantOf(State, Character);
			const std::size_t Record = static_cast<std::size_t>(Character) * CharacterSkills::GrowthRecordSize;
			for (int Number = 0; Number < CharacterSkills::DeathblowCount; ++Number)
			{
				for (int Counter = 0; Counter < DeathblowCounterCount; ++Counter)
				{
					const std::size_t At = Record + static_cast<std::size_t>(Number * DeathblowCounterCount + Counter) * 2;
					const uint16 Threshold = At + 2 <= Growth.size() ? LittleEndian::ReadU16(Growth, At) : uint16{0};
					uint16& Value = Practised.DeathblowCounters[static_cast<std::size_t>(Counter)];
					Value = std::max(Value, Threshold);
				}
			}
			Practised.Character = Character;
			Practised.Status = 0;
			Practised.BattleFlags = 0;
			Practised.Gear = NoGear;
			int Learned = 0;
			for (int Battle = 0; Battle < CharacterSkills::DeathblowCount; ++Battle)
			{
				const uint16 Before = SkillsWord(State, Character, GameStateLayout::Skills::Deathblows);
				const std::unique_ptr<FBattleContext> Context = std::make_unique<FBattleContext>();
				FPsxRandom Random(State.PlayTime() * 0x9E3779B9u + static_cast<uint32>(Battle));
				Context->GameState = &State;
				Context->Random = &Random;
				Context->RuleOptions = Session.Settings().Fixes.BattleRules;
				Context->Combatants[0] = Practised;
				for (std::size_t Slot = 1; Slot < FBattleContext::PartySlotCount; ++Slot)
				{
					// The other slots as felled (nothing learned for them), their character the same (the Infinity attacks' levels).
					Context->Combatants[Slot].Character = Character;
					Context->Combatants[Slot].Status = KnockedOutStatus;
				}
				GiveBattleRewards(*Context, Session.BattleFiles().Growth);
				if (Context->Fault != EBattleFault::None)
				{
					Error = "the battle's result faulted";
					return Learned;
				}
				const uint16 After = SkillsWord(State, Character, GameStateLayout::Skills::Deathblows);
				if (After == Before)
				{
					break;
				}
				Learned += std::popcount(static_cast<uint16>(After & ~Before));
			}
			return Learned;
		}

		/** A number from text; false when it is none. */
		bool NumberOf(const std::string& Text, int64_t& Value)
		{
			if (Text.empty())
			{
				return false;
			}
			char* End = nullptr;
			Value = std::strtoll(Text.c_str(), &End, 10);
			return End != nullptr && *End == '\0';
		}
	}

	FCheatState FSession::CheatState() const
	{
		const FImpl& I = *Impl;
		FCheatState Out;
		Out.bEncountersOff = I.bEncountersOff;
		Out.Turbo = I.Turbo;
		if (!I.Session || !I.Loop || I.bObserved)
		{
			return Out;
		}
		const FGameState& State = I.Session->Game();
		Out.Program = static_cast<int>(I.Loop->Program());
		const bool bProgram = I.Loop->Stage() == EGameLoopStage::Program;
		Out.bCanEdit = bProgram && (I.Loop->Program() == EGameProgram::Field || I.Loop->Program() == EGameProgram::WorldMap);
		Out.bInBattle = bProgram && IsBattleFought(*I.Loop);
		if (Out.bInBattle)
		{
			const FBattleContext& Context = I.Loop->Battle()->Runtime().Context();
			for (std::size_t Slot = FBattleContext::PartySlotCount; Slot < FBattleContext::SlotCount; ++Slot)
			{
				const bool bShown = Context.InBattle[Slot] && Context.Slots[Slot].Presence == 0 && !Context.Escaped[Slot - FBattleContext::PartySlotCount];
				const uint16 Status = Context.Slots[Slot].InGear != 0 ? Context.Combatants[Slot].GearPart.Status : Context.Combatants[Slot].Status;
				Out.EnemiesLeft += bShown && (Status & 0xC000) == 0 ? 1 : 0;
			}
			Out.bCanWin = Context.End == BattleEnd::Running && Out.EnemiesLeft > 0;
		}
		Out.Gold = State.Gold();
		for (const uint8 Character : State.Party())
		{
			if (Character >= FGameState::CharacterCount)
			{
				continue;
			}
			const FBattleCombatant Record = CombatantOf(State, Character);
			FCheatHero Hero;
			Hero.Character = Character;
			Hero.Name = TextOf(State.Name(Character));
			Hero.Level = Record.Level;
			Hero.EtherLevel = Record.EtherLevel;
			Hero.Exp = Record.Exp;
			Hero.EtherExp = Record.EtherExp;
			Hero.ExpToNext = Record.ExpToNext;
			Hero.EtherExpToNext = Record.EtherExpToNext;
			Hero.Hp = Record.Hp;
			Hero.MaxHp = Record.MaxHp;
			Hero.Ep = Record.Ep;
			Hero.MaxEp = Record.MaxEp;
			Hero.Attack = Record.Attack;
			Hero.Defense = Record.Defense;
			Hero.Agility = Record.Agility;
			Hero.Ether = Record.Ether;
			Hero.EtherDefense = Record.EtherDefense;
			Hero.Hit = Record.Hit;
			Hero.Evade = Record.Evade;
			Hero.Deathblows = DeathblowsOf(*I.Session, Character);
			Hero.GearDeathblows = SkillsWord(State, Character, GameStateLayout::Skills::GearDeathblows);
			Hero.ApPerTurn = State.Block()[GameStateLayout::LearnedSkillsOffsetOf(Character) + GameStateLayout::Skills::ApPerTurn];
			if (Record.Gear < GameStateLayout::GearCount)
			{
				Hero.Gear = Record.Gear;
				Hero.GearName = TextOf(State.Name(FGameState::CharacterCount + Record.Gear));
				Hero.GearHp = State.GearHp(Record.Gear).value_or(0);
				Hero.GearMaxHp = State.GearMaxHp(Record.Gear).value_or(0);
				Hero.Fuel = Record.GearPart.Fuel;
				Hero.MaxFuel = Record.GearPart.MaxFuel;
			}
			Out.Party.push_back(std::move(Hero));
		}
		Out.Items = CheatItems(0, true);
		return Out;
	}

	std::vector<FCheatItem> FSession::CheatItems(int List, bool bHeldOnly) const
	{
		const FImpl& I = *Impl;
		std::vector<FCheatItem> Out;
		if (!I.Session || List < 0 || List >= FGameState::InventoryListCount)
		{
			return Out;
		}
		FGameState& State = I.Session->Game();
		const std::span<uint8> Counts = State.InventoryCounts(List);
		const std::span<uint8> Items = State.InventoryItems(List);
		const FMesNameTables& Names = I.Session->Text().NameTables;
		const auto HeldOf = [&](int Id) {
			int Held = 0;
			for (std::size_t Slot = 0; Slot < Counts.size(); ++Slot)
			{
				Held += Items[Slot] == Id ? Counts[Slot] : 0;
			}
			return Held;
		};
		if (bHeldOnly)
		{
			for (std::size_t Slot = 0; Slot < Counts.size(); ++Slot)
			{
				if (Counts[Slot] != 0 && Items[Slot] != 0 && Items[Slot] != FGameState::EmptySlot)
				{
					Out.push_back({Items[Slot], TextOf(Names.String(ItemNameTables[static_cast<std::size_t>(List)], Items[Slot])), Counts[Slot]});
				}
			}
			return Out;
		}
		// Every number the disc's name table names (0 is "none" in every list, FFh an emptied slot).
		for (int Id = 1; Id < 0xFF; ++Id)
		{
			std::string Name = TextOf(Names.String(ItemNameTables[static_cast<std::size_t>(List)], Id));
			if (!Name.empty())
			{
				Out.push_back({Id, std::move(Name), HeldOf(Id)});
			}
		}
		return Out;
	}

	std::string FSession::Cheat(const std::string& Command)
	{
		FImpl& I = *Impl;
		std::vector<std::string> Words;
		for (std::size_t From = 0; From <= Command.size();)
		{
			const std::size_t To = std::min(Command.find(':', From), Command.size());
			Words.push_back(Lowered(Command.substr(From, To - From)));
			From = To + 1;
		}
		const std::string& Verb = Words[0];
		const auto Word = [&](std::size_t At) { return At < Words.size() ? Words[At] : std::string{}; };
		if (Verb == "turbo")
		{
			int64_t Rate = 1;
			if (!NumberOf(Word(1), Rate))
			{
				return "turbo:N";
			}
			SetTurbo(static_cast<int>(Rate));
			return {};
		}
		if (!I.Session || !I.Loop || I.bObserved)
		{
			return "no game running";
		}
		// A replay from F6's state cannot repeat a cheat: counted (asked for, done or not) for the report to say so.
		++I.CheatsSince;
		FGameSession& Session = *I.Session;
		FGameState& State = Session.Game();
		if (Verb == "encounters")
		{
			// Weltall's own setting (its menu's Encounters: None): the field and the world map follow it from their next tick.
			I.bEncountersOff = Word(1) == "0" || Word(1) == "off";
			FPlayerSettings Settings = Session.Settings();
			Settings.Balance.Encounters = I.bEncountersOff ? EEncounterRate::None : EEncounterRate::Original;
			Session.SetSettings(Settings);
			return {};
		}
		const FCheatState Now = CheatState();
		if (Verb == "win")
		{
			if (!Now.bCanWin)
			{
				return Now.bInBattle ? "the battle's end is already decided" : "not in a battle";
			}
			// The core gives the battle's context read-only; it is the program's own (not const), written as the battle's damage
			// writes a felled enemy (ApplyBattleResults: HP 0, the knocked-out bit; a gear's part likewise and the pilot's bit),
			// then the game's own end check (CheckBattleEnd) finds the battle won. The game then plays its victory: the rewards
			// (GiveBattleRewards: the enemies' EXP, gold and drops), the result screen, the return.
			FBattleContext& Context = const_cast<FBattleContext&>(I.Loop->Battle()->Runtime().Context());
			for (std::size_t Slot = FBattleContext::PartySlotCount; Slot < FBattleContext::SlotCount; ++Slot)
			{
				if (!Context.InBattle[Slot] || Context.Slots[Slot].Presence != 0 || Context.Escaped[Slot - FBattleContext::PartySlotCount])
				{
					continue;
				}
				FBattleCombatant& Enemy = Context.Combatants[Slot];
				if (Context.Slots[Slot].InGear != 0)
				{
					Enemy.GearPart.Hp = 0;
					Enemy.GearPart.Status |= KnockedOutStatus;
				}
				else
				{
					Enemy.Hp = 0;
				}
				Enemy.Status |= KnockedOutStatus;
			}
			CheckBattleEnd(Context);
			return Context.End == BattleEnd::Won ? std::string{} : "the battle goes on (an enemy reacts while knocked out)";
		}
		if (!Now.bCanEdit)
		{
			return "only on the field or the world map";
		}
		const auto HeroOf = [&](const std::string& Name) -> int {
			int64_t Number = -1;
			if (NumberOf(Name, Number))
			{
				return Number >= 0 && Number < FGameState::CharacterCount ? static_cast<int>(Number) : -1;
			}
			for (int Character = 0; Character < FGameState::CharacterCount; ++Character)
			{
				if (Lowered(TextOf(State.Name(Character))) == Name)
				{
					return Character;
				}
			}
			return -1;
		};
		int64_t Amount = 0;
		if (Verb == "money" || Verb == "money+")
		{
			if (!NumberOf(Word(1), Amount) || Amount < 0)
			{
				return Verb + ":N";
			}
			// The game's gold, capped where the game caps it.
			const int64_t Gold = Verb == "money" ? Amount : static_cast<int64_t>(State.Gold()) + Amount;
			State.SetGold(static_cast<uint32>(std::min<int64_t>(Gold, MostGold)));
			return {};
		}
		if (Verb == "exp" || Verb == "level")
		{
			if (!NumberOf(Word(2), Amount) || Amount <= 0)
			{
				return Verb + ":<hero>:N";
			}
			if (Verb == "exp" && Word(1) == "party")
			{
				// The party's battle: the members share it as the game shares a battle's EXP.
				std::array<uint8, FBattleContext::PartySlotCount> Members{};
				const std::array<uint8, 3> Party = State.Party();
				for (std::size_t Slot = 0; Slot < Members.size(); ++Slot)
				{
					Members[Slot] = Party[Slot] < FGameState::CharacterCount ? Party[Slot] : FBattleContext::NoCharacter;
				}
				return GiveExpAsBattle(Session, Members, static_cast<uint32>(std::min<int64_t>(Amount, 0x7FFFFFFF)));
			}
			const int Hero = HeroOf(Word(1));
			if (Hero < 0)
			{
				return "no such hero: " + Word(1);
			}
			const std::array<uint8, FBattleContext::PartySlotCount> Alone{static_cast<uint8>(Hero), FBattleContext::NoCharacter, FBattleContext::NoCharacter};
			if (Verb == "exp")
			{
				// The hero's battle alone: the whole of it the hero's.
				return GiveExpAsBattle(Session, Alone, static_cast<uint32>(std::min<int64_t>(Amount, 0x7FFFFFFF)));
			}
			// A level at a time: the hero alone in a battle worth what the record says is left to the next level (twice that
			// where the rules share EXP between the pools).
			for (int64_t Level = 0; Level < Amount; ++Level)
			{
				const FBattleCombatant Before = CombatantOf(State, static_cast<uint8>(Hero));
				if (Before.Level >= MostLevel)
				{
					return Level == 0 ? "already at the last level" : std::string{};
				}
				const uint32 Left = std::max<uint32>(Before.ExpToNext, 1);
				const uint32 Total = (State.StoryFlags() & NormalExpRules) != 0 ? Left : Left * 2;
				if (std::string Error = GiveExpAsBattle(Session, Alone, Total); !Error.empty())
				{
					return Error;
				}
				if (CombatantOf(State, static_cast<uint8>(Hero)).Level <= Before.Level)
				{
					return "the level did not rise";
				}
			}
			return {};
		}
		if (Verb == "fill")
		{
			// HP and EP back to their highest, as the field's FE DB (RestoreCharacter) does it.
			for (const uint8 Character : State.Party())
			{
				if (Character >= FGameState::CharacterCount || (Word(1) != "party" && HeroOf(Word(1)) != Character))
				{
					continue;
				}
				using EPoints = FGameState::ECharacterPoints;
				State.SetCharacterPoints(Character, EPoints::Hp, State.CharacterPoints(Character, EPoints::MaxHp));
				State.SetCharacterPoints(Character, EPoints::Ep, State.CharacterPoints(Character, EPoints::MaxEp));
			}
			return {};
		}
		if (Verb == "deathblows")
		{
			// Every Deathblow the game's own learning routine teaches the character now (LearnDeathblowsAsBattle says how).
			std::string Error;
			int Learned = 0;
			bool bAny = false;
			for (const uint8 Character : State.Party())
			{
				if (Character >= FGameState::CharacterCount || (Word(1) != "party" && HeroOf(Word(1)) != Character))
				{
					continue;
				}
				bAny = true;
				if (Character == ChuChuCharacter || Character == MariaCharacter)
				{
					continue;
				}
				Learned += LearnDeathblowsAsBattle(Session, Character, Error);
				if (!Error.empty())
				{
					return Error;
				}
			}
			return !bAny ? "no such hero in the party: " + Word(1) : Learned == 0 ? "nothing more to learn now" : std::string{};
		}
		if (Verb == "gears")
		{
			// Every gear's HP and fuel to their highest: the game's own routine (the field's FE A4, FGameState::RestoreGears).
			State.RestoreGears();
			return {};
		}
		if (Verb == "item")
		{
			int64_t List = 0, Id = 0, Count = 0;
			if (!NumberOf(Word(1), List) || !NumberOf(Word(2), Id) || !NumberOf(Word(3), Count) || List < 0 || List >= FGameState::InventoryListCount || Id < 1
				|| Id >= 0xFF || Count < 0)
			{
				return "item:<list 0-4>:<id>:<count>";
			}
			// As the field's GiveItem (8C) finds a place: the slot holding the item, else the first free one (a full list takes
			// nothing); at most 99. None left: the slot emptied as the game's TakeItem leaves it (its item FFh).
			const std::span<uint8> Counts = State.InventoryCounts(static_cast<int32>(List));
			const std::span<uint8> Items = State.InventoryItems(static_cast<int32>(List));
			std::ptrdiff_t Slot = -1;
			for (std::size_t At = 0; At < Counts.size() && Slot < 0; ++At)
			{
				Slot = Items[At] == Id && Counts[At] != 0 ? static_cast<std::ptrdiff_t>(At) : -1;
			}
			if (Slot < 0 && Count == 0)
			{
				return {};
			}
			for (std::size_t At = 0; At < Counts.size() && Slot < 0; ++At)
			{
				Slot = Counts[At] == 0 || Items[At] == 0 ? static_cast<std::ptrdiff_t>(At) : -1;
			}
			if (Slot < 0)
			{
				return "the list is full";
			}
			Items[static_cast<std::size_t>(Slot)] = Count == 0 ? FGameState::EmptySlot : static_cast<uint8>(Id);
			Counts[static_cast<std::size_t>(Slot)] = static_cast<uint8>(std::min<int64_t>(Count, MostOfAnItem));
			return {};
		}
		return "unknown cheat: " + Command;
	}

	void FSession::SetTurbo(int Rate)
	{
		Impl->Turbo = std::clamp(Rate, 1, 8);
	}

	int FSession::GamePace() const
	{
		const FImpl& I = *Impl;
		if (I.Turbo <= 1 || !I.Session || !I.Loop)
		{
			return 1;
		}
		// Where Weltall's own fast-forward runs (GamePace.cpp): a battle being fought, or the field or the world map ticking
		// (not paused, not in a menu or its shade, not the title); movies, menus and the result screen keep the game's pace.
		FPlayerSettings Settings = I.Session->Settings();
		Settings.Balance.bExplorationFastForward = true;
		return IsBattleFought(*I.Loop) || CanFastForwardExploration(*I.Loop, Settings) ? I.Turbo : 1;
	}

	int FSession::ProgramRuns() const
	{
		return Impl->Loop ? Impl->Loop->ProgramRuns() : 0;
	}
}
